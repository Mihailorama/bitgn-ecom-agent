"""Mixed-model parallel benchmark runner.

Starts one BitGN run, then routes each task to either Claude CLI or Codex CLI
after `start_trial()` reveals the task_id. This keeps leaderboard accounting in
one run while allowing separate concurrency caps for simple and complex tasks.

Example:
  MIXED_PARALLEL=12 MIXED_CLAUDE_LIMIT=6 MIXED_CODEX_LIMIT=6 \
  CLAUDE_MODEL_ID=claude:sonnet CODEX_MODEL_ID=codex:gpt-5.3-codex \
  SWEEP_LOG_DIR=artifacts/sweeps/mixed-r1 uv run python run_mixed_parallel.py
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from bitgn.harness_connect import HarnessServiceClientSync
from bitgn.harness_pb2 import (
    EndTrialRequest,
    EvalPolicy,
    GetBenchmarkRequest,
    GetRunRequest,
    StartRunRequest,
    StartTrialRequest,
    StatusRequest,
    SubmitRunRequest,
)
from connectrpc.errors import ConnectError

from agent import run_agent
from degradation_gate import (
    build_sweep_report,
    format_gate_summary,
    points_for_gate,
    write_sweep_report,
)
from harness_retry import retry_delay_for_connect_error
from harness_scoring import merge_submit_scores, submit_score_available


BITGN_URL = os.getenv("BITGN_HOST") or os.getenv("BENCHMARK_HOST") or "https://api.bitgn.com"
BITGN_API_KEY = os.getenv("BITGN_API_KEY") or ""
BENCH_ID = os.getenv("BENCH_ID") or os.getenv("BENCHMARK_ID") or "bitgn/ecom1-dev"
CLAUDE_MODEL_ID = os.getenv("CLAUDE_MODEL_ID", "claude:sonnet")
CODEX_MODEL_ID = os.getenv("CODEX_MODEL_ID", "codex:gpt-5.3-codex")
MIXED_PARALLEL = int(os.getenv("MIXED_PARALLEL", "12"))
MIXED_CLAUDE_LIMIT = int(os.getenv("MIXED_CLAUDE_LIMIT", "6"))
MIXED_CODEX_LIMIT = int(os.getenv("MIXED_CODEX_LIMIT", "6"))
LOG_DIR = os.getenv("SWEEP_LOG_DIR", "/tmp/mixed_sweep_logs")
LEADERBOARD_BEST_POINTS = float(os.getenv("LEADERBOARD_BEST_POINTS", "50.0"))
LEADERBOARD_BEST_MAX_POINTS = int(os.getenv("LEADERBOARD_BEST_MAX_POINTS", "50"))
_BEST_SECONDS_RAW = os.getenv("LEADERBOARD_BEST_SECONDS", "3603")
LEADERBOARD_BEST_SECONDS = float(_BEST_SECONDS_RAW) if _BEST_SECONDS_RAW else None
MIN_ACCEPTED_POINTS = float(
    os.getenv(
        "MIN_ACCEPTED_POINTS",
        os.getenv("MIN_ACCEPTED_SOLVED", str(LEADERBOARD_BEST_POINTS)),
    )
)
MIN_ACCEPTED_PCT = float(os.getenv("MIN_ACCEPTED_PCT", "98"))

# Keep known fragile / high-value families on Codex by default. Everything else
# is diagnostic Claude traffic unless overridden by env.
DEFAULT_CODEX_TASKS = frozenset(
    "t02 t06 t16 t22 t31 t32 t33 t36 t38 t39 t40 t43 t47 t48 t49 t50".split()
)


def _retry(fn, attempts: int = 5):
    delay = 1.0
    for i in range(attempts):
        try:
            return fn()
        except ConnectError as exc:
            if i == attempts - 1:
                raise
            time.sleep(retry_delay_for_connect_error(exc, delay))
            delay = min(delay * 2, 8.0)


def parse_task_set(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {part.strip() for part in raw.replace(",", " ").split() if part.strip()}


def configured_codex_tasks() -> set[str]:
    raw = os.getenv("MIXED_CODEX_TASKS")
    return parse_task_set(raw) if raw else set(DEFAULT_CODEX_TASKS)


def configured_claude_tasks() -> set[str]:
    return parse_task_set(os.getenv("MIXED_CLAUDE_TASKS"))


def configured_task_model_overrides() -> dict[str, str]:
    raw = os.getenv("MIXED_TASK_MODEL_OVERRIDES", "").strip()
    if not raw:
        return {}
    out: dict[str, str] = {}
    for part in raw.split(","):
        token = part.strip()
        if not token or "=" not in token:
            continue
        task_id, model_id = token.split("=", 1)
        task_id = task_id.strip()
        model_id = model_id.strip()
        if not task_id or not model_id:
            continue
        out[task_id] = model_id
    return out


def choose_model_for_task(
    task_id: str,
    *,
    claude_model: str = CLAUDE_MODEL_ID,
    codex_model: str = CODEX_MODEL_ID,
    claude_tasks: set[str] | None = None,
    codex_tasks: set[str] | None = None,
    task_model_overrides: dict[str, str] | None = None,
) -> str:
    claude_tasks = configured_claude_tasks() if claude_tasks is None else claude_tasks
    codex_tasks = configured_codex_tasks() if codex_tasks is None else codex_tasks
    task_model_overrides = (
        configured_task_model_overrides()
        if task_model_overrides is None
        else task_model_overrides
    )
    if task_id in task_model_overrides:
        return task_model_overrides[task_id]
    if task_id in claude_tasks:
        return claude_model
    if task_id in codex_tasks:
        return codex_model
    return claude_model


def model_slot(model_id: str) -> str:
    low = model_id.lower()
    if low.startswith(("claude:", "claude-cli:", "sonnet", "opus", "haiku")):
        return "claude"
    if low.startswith(("codex:", "codex-cli:")):
        return "codex"
    return "codex"


def report_leaderboard_seconds(report: dict[str, Any]) -> float | None:
    timing = report.get("timing")
    if not isinstance(timing, dict):
        return None
    seconds = timing.get("platform_open_seconds_sum")
    if not isinstance(seconds, (int, float)):
        return None
    return float(seconds)


def should_submit_leaderboard(
    report: dict[str, Any],
    task_filter: list[str],
    *,
    best_points: float = LEADERBOARD_BEST_POINTS,
    best_max_points: int = LEADERBOARD_BEST_MAX_POINTS,
    best_time_seconds: float | None = LEADERBOARD_BEST_SECONDS,
) -> tuple[bool, str]:
    if task_filter:
        return False, "subset run"
    if not report.get("accepted"):
        reasons = "; ".join(str(reason) for reason in report.get("reasons") or [])
        return False, reasons or "gate rejected"

    points = points_for_gate(float(report.get("points") or 0.0))
    best_points = points_for_gate(best_points)
    epsilon = 1e-6
    if points > best_points + epsilon:
        return True, f"points improved {points:.2f} > {best_points:.2f}"
    if points < best_points - epsilon:
        return False, f"points {points:.2f} below leaderboard best {best_points:.2f}"

    max_points = int(report.get("max_points") or 0)
    if max_points != best_max_points:
        return False, f"same points but denominator changed {max_points} != {best_max_points}"

    current_seconds = report_leaderboard_seconds(report)
    if current_seconds is None:
        return False, "same points but platform_open_seconds_sum is missing"
    if best_time_seconds is None:
        return False, "same points but leaderboard best time is not configured"
    if current_seconds < best_time_seconds - 0.5:
        return True, (
            f"same points and faster leaderboard time "
            f"{current_seconds:.0f}s < {best_time_seconds:.0f}s"
        )
    return False, (
        f"same points but not faster "
        f"{current_seconds:.0f}s >= {best_time_seconds:.0f}s"
    )


def _acquire_for_model(model_id: str, semaphores: dict[str, Any]):
    slot = model_slot(model_id)
    sem = semaphores[slot]
    sem.acquire()
    return slot, sem


def planned_task_id_for_trial(
    trial_id: str,
    trial_task_ids: dict[str, str] | set[str],
) -> str | None:
    if isinstance(trial_task_ids, dict):
        return trial_task_ids.get(trial_id)
    if trial_id in trial_task_ids:
        return trial_id
    return None


@dataclass
class SlotReservation:
    model_id: str
    slot: str
    sem: Any
    slot_wait: float

    def release(self) -> None:
        self.sem.release()


def reserve_slot_for_known_trial_id(
    trial_id: str,
    trial_task_ids: dict[str, str] | set[str],
    semaphores: dict[str, Any],
    *,
    claude_model: str = CLAUDE_MODEL_ID,
    codex_model: str = CODEX_MODEL_ID,
    claude_tasks: set[str] | None = None,
    codex_tasks: set[str] | None = None,
    task_model_overrides: dict[str, str] | None = None,
) -> SlotReservation | None:
    task_id = planned_task_id_for_trial(trial_id, trial_task_ids)
    if task_id is None:
        return None
    model_id = choose_model_for_task(
        task_id,
        claude_model=claude_model,
        codex_model=codex_model,
        claude_tasks=claude_tasks,
        codex_tasks=codex_tasks,
        task_model_overrides=task_model_overrides,
    )
    wait0 = time.time()
    slot, sem = _acquire_for_model(model_id, semaphores)
    return SlotReservation(model_id, slot, sem, time.time() - wait0)


def run_one(
    trial_id: str,
    task_filter: list[str],
    semaphores: dict[str, Any],
    trial_task_ids: dict[str, str],
):
    try:
        return _run_one(trial_id, task_filter, semaphores, trial_task_ids)
    except Exception as exc:
        return (trial_id, None, None, f"worker error: {exc!r}"[:200], 0.0, "", 0.0, 0.0)


def _run_one(
    trial_id: str,
    task_filter: list[str],
    semaphores: dict[str, Any],
    trial_task_ids: dict[str, str],
):
    client = HarnessServiceClientSync(BITGN_URL)
    planned_task_id = planned_task_id_for_trial(trial_id, trial_task_ids)
    if task_filter and planned_task_id and planned_task_id not in task_filter:
        return (planned_task_id, "skip", None, None, 0.0, "", 0.0, 0.0)

    reservation = reserve_slot_for_known_trial_id(trial_id, trial_task_ids, semaphores)
    try:
        start0 = time.time()
        trial = _retry(lambda: client.start_trial(StartTrialRequest(trial_id=trial_id)))
        trial_open0 = time.time()
    except ConnectError as exc:
        if reservation:
            reservation.release()
        start_secs = time.time() - start0
        return (trial_id, None, None, f"start_trial: {exc.code} {exc.message}", start_secs, "", 0.0, 0.0)

    if task_filter and trial.task_id not in task_filter:
        if reservation:
            reservation.release()
        platform_open = time.time() - trial_open0
        return (trial.task_id, "skip", None, None, 0.0, "", platform_open, 0.0)

    model_id = choose_model_for_task(trial.task_id)
    if reservation and reservation.model_id == model_id:
        slot, sem = reservation.slot, reservation.sem
        slot_wait = reservation.slot_wait
    else:
        if reservation:
            reservation.release()
        wait0 = time.time()
        slot, sem = _acquire_for_model(model_id, semaphores)
        slot_wait = time.time() - wait0
    log_path = os.path.join(LOG_DIR, f"{trial.task_id}.log")
    t0 = time.time()
    agent_error = None
    try:
        with open(log_path, "w", encoding="utf-8") as fh, redirect_stdout(fh):
            print(f"TASK {trial.task_id} (model {model_id}, slot {slot})")
            print(f"INSTRUCTION: {trial.instruction}\n{'-' * 80}")
            try:
                run_agent(model_id, trial.harness_url, trial.instruction)
            except Exception as exc:
                agent_error = f"agent crashed: {exc!r}"
                print(agent_error)
    finally:
        sem.release()
    agent_elapsed = time.time() - t0

    try:
        res = _retry(lambda: client.end_trial(EndTrialRequest(trial_id=trial.trial_id)))
    except ConnectError as exc:
        platform_open = time.time() - trial_open0
        return (
            trial.task_id,
            None,
            None,
            f"end_trial: {exc.code} {exc.message}",
            agent_elapsed,
            model_id,
            platform_open,
            slot_wait,
        )

    platform_open = time.time() - trial_open0
    if agent_error:
        return (trial.task_id, None, None, agent_error, agent_elapsed, model_id, platform_open, slot_wait)
    score = res.score if res.score_available else None
    return (trial.task_id, score, list(res.score_detail), None, agent_elapsed, model_id, platform_open, slot_wait)


def main() -> None:
    task_filter = sys.argv[1:]
    os.makedirs(LOG_DIR, exist_ok=True)

    client = HarnessServiceClientSync(BITGN_URL)
    print("Connecting to BitGN:", _retry(lambda: client.status(StatusRequest())).status)
    bench = _retry(lambda: client.get_benchmark(GetBenchmarkRequest(benchmark_id=BENCH_ID)))
    print(
        f"{EvalPolicy.Name(bench.policy)} {bench.benchmark_id}: {len(bench.tasks)} tasks "
        f"| claude {CLAUDE_MODEL_ID} x{MIXED_CLAUDE_LIMIT} | "
        f"codex {CODEX_MODEL_ID} x{MIXED_CODEX_LIMIT} | "
        f"workers {MIXED_PARALLEL} | logs {LOG_DIR}"
    )

    route = {
        "claude_model": CLAUDE_MODEL_ID,
        "codex_model": CODEX_MODEL_ID,
        "claude_tasks": sorted(configured_claude_tasks()),
        "codex_tasks": sorted(configured_codex_tasks()),
        "task_model_overrides": dict(sorted(configured_task_model_overrides().items())),
        "default_model": CLAUDE_MODEL_ID,
    }
    Path(LOG_DIR, "route_manifest.json").write_text(
        json.dumps(route, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    run = client.start_run(
        StartRunRequest(
            name="@ai_nuts_and_bolts mixed",
            benchmark_id=BENCH_ID,
            api_key=BITGN_API_KEY,
        )
    )

    manager = mp.Manager()
    semaphores = {
        "claude": manager.BoundedSemaphore(MIXED_CLAUDE_LIMIT),
        "codex": manager.BoundedSemaphore(MIXED_CODEX_LIMIT),
    }
    benchmark_task_ids = {task.task_id for task in bench.tasks}
    run_head = _retry(lambda: client.get_run(GetRunRequest(run_id=run.run_id)))
    trial_task_ids = {
        trial.trial_id: trial.task_id
        for trial in run_head.trials
        if trial.trial_id and trial.task_id
    }
    if not trial_task_ids:
        trial_task_ids = {trial_id: trial_id for trial_id in run.trial_ids if trial_id in benchmark_task_ids}

    results = []
    submit_result = None
    submit_error = None
    ctx = mp.get_context("spawn")
    wall0 = time.time()
    try:
        with ProcessPoolExecutor(max_workers=MIXED_PARALLEL, mp_context=ctx) as pool:
            futures = {
                pool.submit(run_one, tid, task_filter, semaphores, trial_task_ids): tid
                for tid in run.trial_ids
            }
            for fut in as_completed(futures):
                task_id, score, detail, err, secs, model_id, platform_secs, wait_secs = fut.result()
                if score == "skip":
                    continue
                results.append((task_id, score, detail, err, secs, model_id, platform_secs, wait_secs))
                tag = f"{score:.2f}" if isinstance(score, (int, float)) else (err or "n/a")
                wait_part = f", wait {wait_secs:.0f}s" if wait_secs >= 0.5 else ""
                print(
                    f"[done] {task_id}: {tag} "
                    f"({secs:.0f}s agent, {platform_secs:.0f}s open{wait_part}, {model_id})",
                    flush=True,
                )
    finally:
        try:
            submit_result = _retry(
                lambda: client.submit_run(SubmitRunRequest(run_id=run.run_id, force=True))
            )
        except ConnectError as exc:
            submit_error = f"submit_run: {exc.code} {exc.message}"
    wall = time.time() - wall0
    if submit_result is not None:
        results = merge_submit_scores(results, submit_result, task_filter=set(task_filter))

    print("\n==== SUMMARY ====")
    if submit_error:
        print(f"RUN CLOSE ERROR: {submit_error}")
    elif submit_result is not None:
        status = "batch scores available" if submit_score_available(submit_result) else "batch scores unavailable"
        print(f"RUN CLOSED: run_id={run.run_id} ({status})")
    scored, times, platform_times, slot_waits = [], [], [], []
    for task_id, score, detail, err, secs, model_id, platform_secs, wait_secs in sorted(results):
        times.append(secs)
        platform_times.append(platform_secs)
        slot_waits.append(wait_secs)
        if isinstance(score, (int, float)):
            scored.append(score)
            line = (
                f"{task_id}: {score:.2f} "
                f"({secs:.0f}s agent, {platform_secs:.0f}s open, {model_id})"
            )
            if wait_secs >= 0.5:
                line += f" wait_slot={wait_secs:.0f}s"
            if score < 1.0 and detail:
                line += "  | " + " ; ".join(detail)[:240]
        else:
            line = f"{task_id}: ERROR {err} ({model_id})"
        print(line)

    if scored:
        passed = sum(1 for s in scored if s >= 0.999)
        points = sum(scored)
        pct = points / len(scored) * 100
        avg = sum(times) / len(times) if times else 0
        slowest = max(times) if times else 0
        platform_total = sum(platform_times)
        wait_total = sum(slot_waits)
        print(
            f"\nFINAL: {pct:.2f}%  ({points:.2f}/{len(scored)} points, "
            f"{passed}/{len(scored)} perfect)\n"
            f"SPEED: wall {wall:.0f}s | avg/task {avg:.0f}s | slowest {slowest:.0f}s | "
            f"platform_open_sum {platform_total:.0f}s | slot_wait_sum {wait_total:.0f}s | "
            f"workers {MIXED_PARALLEL} | claude_limit {MIXED_CLAUDE_LIMIT} | "
            f"codex_limit {MIXED_CODEX_LIMIT}"
        )

    report_input = [(tid, score, detail, err, secs) for tid, score, detail, err, secs, _, _, _ in results]
    report = build_sweep_report(
        report_input,
        LOG_DIR,
        min_points=MIN_ACCEPTED_POINTS,
        min_pct=MIN_ACCEPTED_PCT,
    )
    report["mixed_route"] = route
    timing_by_task = {
        tid: {
            "agent_seconds": round(float(secs or 0.0), 3),
            "platform_open_seconds": round(float(platform_secs or 0.0), 3),
            "slot_wait_seconds": round(float(wait_secs or 0.0), 3),
            "model_id": model_id,
        }
        for tid, _score, _detail, _err, secs, model_id, platform_secs, wait_secs in results
    }
    for task in report["tasks"]:
        task.update(timing_by_task.get(task["task_id"], {}))
    report["timing"] = {
        "wall_seconds": round(float(wall), 3),
        "agent_seconds_sum": round(sum(times), 3),
        "platform_open_seconds_sum": round(sum(platform_times), 3),
        "slot_wait_seconds_sum": round(sum(slot_waits), 3),
        "agent_seconds_max": round(max(times), 3) if times else 0.0,
        "platform_open_seconds_max": round(max(platform_times), 3) if platform_times else 0.0,
        "slot_wait_seconds_max": round(max(slot_waits), 3) if slot_waits else 0.0,
    }
    print(format_gate_summary(report))
    should_submit, submit_reason = should_submit_leaderboard(report, task_filter)
    if should_submit:
        print(f"leaderboard gate: eligible after run close ({submit_reason}) run_id={run.run_id}")
    else:
        print(f"leaderboard gate: rejected after run close ({submit_reason}) run_id={run.run_id}")
    report["leaderboard_submit"] = {
        "eligible": should_submit,
        "reason": submit_reason,
        "run_id": run.run_id,
        "submitted": submit_result is not None,
        "submit_error": submit_error,
        "submit_required_for_score": True,
    }
    report_path = write_sweep_report(report, LOG_DIR)
    print(f"gate report: {report_path}")
    print(f"route manifest: {LOG_DIR}/route_manifest.json")
    print(f"per-task logs: {LOG_DIR}/<task>.log")


if __name__ == "__main__":
    main()
