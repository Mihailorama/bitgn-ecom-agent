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


def run_one(trial_id: str, task_filter: list[str]):
    """Worker: start one trial, run the agent into its own log, score it."""
    client = HarnessServiceClientSync(BITGN_URL)
    try:
        trial = client.start_trial(StartTrialRequest(trial_id=trial_id))
    except ConnectError as exc:
        return (trial_id, None, None, f"start_trial: {exc.code} {exc.message}")

    if task_filter and trial.task_id not in task_filter:
        return (trial.task_id, "skip", None, None)

    log_path = os.path.join(LOG_DIR, f"{trial.task_id}.log")
    with open(log_path, "w", encoding="utf-8") as fh, redirect_stdout(fh):
        print(f"TASK {trial.task_id} (model {MODEL_ID})")
        print(f"INSTRUCTION: {trial.instruction}\n{'-' * 80}")
        try:
            run_agent(MODEL_ID, trial.harness_url, trial.instruction)
        except Exception as exc:  # keep the sweep going if one task throws
            print(f"agent crashed: {exc!r}")

    try:
        res = client.end_trial(EndTrialRequest(trial_id=trial.trial_id))
    except ConnectError as exc:
        return (trial.task_id, None, None, f"end_trial: {exc.code} {exc.message}")

    score = res.score if res.score_available else None
    return (trial.task_id, score, list(res.score_detail), None)


def main() -> None:
    task_filter = sys.argv[1:]
    os.makedirs(LOG_DIR, exist_ok=True)

    client = HarnessServiceClientSync(BITGN_URL)
    print("Connecting to BitGN:", client.status(StatusRequest()).status)
    bench = client.get_benchmark(GetBenchmarkRequest(benchmark_id=BENCH_ID))
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
    try:
        with ProcessPoolExecutor(max_workers=PARALLEL, mp_context=ctx) as pool:
            futures = {
                pool.submit(run_one, tid, task_filter): tid for tid in run.trial_ids
            }
            for fut in as_completed(futures):
                task_id, score, detail, err = fut.result()
                if score == "skip":
                    continue
                results.append((task_id, score, detail, err))
                tag = f"{score:.2f}" if isinstance(score, (int, float)) else (err or "n/a")
                print(f"[done] {task_id}: {tag}", flush=True)
    finally:
        client.submit_run(SubmitRunRequest(run_id=run.run_id, force=True))

    print("\n==== SUMMARY ====")
    scored = []
    for task_id, score, detail, err in sorted(results):
        if isinstance(score, (int, float)):
            scored.append(score)
            line = f"{task_id}: {score:.2f}"
            if score < 1.0 and detail:
                line += "  | " + " ; ".join(detail)[:240]
        else:
            line = f"{task_id}: ERROR {err}"
        print(line)

    if scored:
        passed = sum(1 for s in scored if s >= 0.999)
        print(
            f"\nFINAL: {sum(scored) / len(scored) * 100:.2f}%  "
            f"({passed}/{len(scored)} perfect, {len(scored)} scored)"
        )
    print(f"per-task logs: {LOG_DIR}/<task>.log")


if __name__ == "__main__":
    main()
