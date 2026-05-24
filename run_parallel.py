"""Parallel benchmark runner - same flow as main.py but runs trials concurrently.

Trials are independent (each gets its own harness_url), so a process pool cuts a
44-task sweep from ~2h to ~15min and speeds up every iteration. Each task's full
trace goes to its own log under SWEEP_LOG_DIR; the parent prints a score summary.

  uv run python run_parallel.py            # full benchmark
  uv run python run_parallel.py t13 t17    # subset
  PARALLEL=8 MODEL_ID=claude:sonnet make sweep
"""

import multiprocessing as mp
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout

from dotenv import load_dotenv

load_dotenv()

from bitgn.harness_connect import HarnessServiceClientSync
from bitgn.harness_pb2 import (
    EndTrialRequest,
    EvalPolicy,
    GetBenchmarkRequest,
    StartRunRequest,
    StartTrialRequest,
    StatusRequest,
    SubmitRunRequest,
)
from connectrpc.errors import ConnectError

from agent import run_agent

BITGN_URL = os.getenv("BITGN_HOST") or os.getenv("BENCHMARK_HOST") or "https://api.bitgn.com"
BITGN_API_KEY = os.getenv("BITGN_API_KEY") or ""
BENCH_ID = os.getenv("BENCH_ID") or os.getenv("BENCHMARK_ID") or "bitgn/ecom1-dev"
MODEL_ID = os.getenv("MODEL_ID") or "gpt-5.5"
PARALLEL = int(os.getenv("PARALLEL", "6"))
LOG_DIR = os.getenv("SWEEP_LOG_DIR", "/tmp/sweep_logs")


def _retry(fn, attempts: int = 5):
    """Retry idempotent control-plane calls through transient TLS/network blips
    (e.g. brief cert-rotation clock skew) with exponential backoff."""
    delay = 1.0
    for i in range(attempts):
        try:
            return fn()
        except ConnectError:
            if i == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 8.0)


def run_one(trial_id: str, task_filter: list[str]):
    """Worker entry point. Wrapped so no worker exception can propagate through
    fut.result() and abort the whole sweep - a failed worker becomes an error
    row instead."""
    try:
        return _run_one(trial_id, task_filter)
    except Exception as exc:  # never let one worker kill the pool
        return (trial_id, None, None, f"worker error: {exc!r}"[:200], 0.0)


def _run_one(trial_id: str, task_filter: list[str]):
    """Start one trial, run the agent into its own log, score it."""
    client = HarnessServiceClientSync(BITGN_URL)
    try:
        trial = _retry(lambda: client.start_trial(StartTrialRequest(trial_id=trial_id)))
    except ConnectError as exc:
        return (trial_id, None, None, f"start_trial: {exc.code} {exc.message}", 0.0)

    # End filtered-out trials immediately (task_id is only known after start) so a
    # subset run does not leak dozens of open trials on the harness.
    if task_filter and trial.task_id not in task_filter:
        try:
            _retry(lambda: client.end_trial(EndTrialRequest(trial_id=trial.trial_id)))
        except ConnectError:
            pass
        return (trial.task_id, "skip", None, None, 0.0)

    log_path = os.path.join(LOG_DIR, f"{trial.task_id}.log")
    t0 = time.time()
    agent_error = None
    with open(log_path, "w", encoding="utf-8") as fh, redirect_stdout(fh):
        print(f"TASK {trial.task_id} (model {MODEL_ID})")
        print(f"INSTRUCTION: {trial.instruction}\n{'-' * 80}")
        try:
            run_agent(MODEL_ID, trial.harness_url, trial.instruction)
        except Exception as exc:  # run_agent self-guards; reaching here means even
            agent_error = f"agent crashed: {exc!r}"  # its fallback answer failed
            print(agent_error)
    elapsed = time.time() - t0

    try:
        res = _retry(lambda: client.end_trial(EndTrialRequest(trial_id=trial.trial_id)))
    except ConnectError as exc:
        return (trial.task_id, None, None, f"end_trial: {exc.code} {exc.message}", elapsed)

    # Surface a genuinely blank trial (the agent never managed to answer) as an
    # error, not as an ordinary 0.0 that hides among legitimately-wrong answers.
    if agent_error:
        return (trial.task_id, None, None, agent_error, elapsed)
    score = res.score if res.score_available else None
    return (trial.task_id, score, list(res.score_detail), None, elapsed)


def main() -> None:
    task_filter = sys.argv[1:]
    os.makedirs(LOG_DIR, exist_ok=True)

    client = HarnessServiceClientSync(BITGN_URL)
    print("Connecting to BitGN:", _retry(lambda: client.status(StatusRequest())).status)
    bench = _retry(lambda: client.get_benchmark(GetBenchmarkRequest(benchmark_id=BENCH_ID)))
    print(
        f"{EvalPolicy.Name(bench.policy)} {bench.benchmark_id}: {len(bench.tasks)} tasks "
        f"| model {MODEL_ID} | parallel {PARALLEL} | logs {LOG_DIR}"
    )

    run = client.start_run(
        StartRunRequest(
            name=f"ECOM SGR parallel ({MODEL_ID})",
            benchmark_id=BENCH_ID,
            api_key=BITGN_API_KEY,
        )
    )

    results = []
    ctx = mp.get_context("spawn")  # avoid fork-after-threads with the gRPC client
    wall0 = time.time()
    try:
        with ProcessPoolExecutor(max_workers=PARALLEL, mp_context=ctx) as pool:
            futures = {
                pool.submit(run_one, tid, task_filter): tid for tid in run.trial_ids
            }
            for fut in as_completed(futures):
                task_id, score, detail, err, secs = fut.result()
                if score == "skip":
                    continue
                results.append((task_id, score, detail, err, secs))
                tag = f"{score:.2f}" if isinstance(score, (int, float)) else (err or "n/a")
                print(f"[done] {task_id}: {tag} ({secs:.0f}s)", flush=True)
    finally:
        client.submit_run(SubmitRunRequest(run_id=run.run_id, force=True))
    wall = time.time() - wall0

    print("\n==== SUMMARY ====")
    scored, times = [], []
    for task_id, score, detail, err, secs in sorted(results):
        times.append(secs)
        if isinstance(score, (int, float)):
            scored.append(score)
            line = f"{task_id}: {score:.2f} ({secs:.0f}s)"
            if score < 1.0 and detail:
                line += "  | " + " ; ".join(detail)[:240]
        else:
            line = f"{task_id}: ERROR {err}"
        print(line)

    pct = passed = 0
    if scored:
        passed = sum(1 for s in scored if s >= 0.999)
        pct = sum(scored) / len(scored) * 100
        avg = sum(times) / len(times) if times else 0
        slowest = max(times) if times else 0
        print(
            f"\nFINAL: {pct:.2f}%  ({passed}/{len(scored)} perfect, {len(scored)} scored)\n"
            f"SPEED: wall {wall:.0f}s | avg/task {avg:.0f}s | slowest {slowest:.0f}s | "
            f"parallel {PARALLEL}"
        )
        # Record score-vs-speed per model for full sweeps (skip partial reruns).
        if not task_filter:
            _append_result(MODEL_ID, pct, passed, len(scored), wall, avg, PARALLEL)
    print(f"per-task logs: {LOG_DIR}/<task>.log")


def _append_result(model, pct, passed, total, wall, avg, parallel):
    import datetime

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "RESULTS.md")
    header = (
        "# Model score vs speed (bitgn/ecom1-dev)\n\n"
        "| date (UTC) | model | score | perfect | wall | avg/task | parallel |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(header)
    row = (
        f"| {datetime.datetime.now(datetime.UTC):%Y-%m-%d %H:%M} | {model} | {pct:.1f}% | "
        f"{passed}/{total} | {wall:.0f}s | {avg:.0f}s | {parallel} |\n"
    )
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(row)
    print(f"recorded result to {path}")


if __name__ == "__main__":
    main()
