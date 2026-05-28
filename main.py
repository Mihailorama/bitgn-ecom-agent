import os
import textwrap

from dotenv import load_dotenv

# Load a local .env (gitignored) so keys can live in a file instead of the shell.
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
from harness_scoring import merge_submit_scores, submit_score_available


BITGN_URL = (
    os.getenv("BITGN_HOST")
    or os.getenv("BENCHMARK_HOST")
    or "https://api.bitgn.com"
)
BITGN_API_KEY = os.getenv("BITGN_API_KEY") or ""
BENCH_ID = os.getenv("BENCH_ID") or os.getenv("BENCHMARK_ID") or "bitgn/ecom1-dev"
# Neutral default. Override per context (provider routing lives in llm.py):
#   tests      -> MODEL_ID=claude:opus            (Claude OAuth via claude CLI, no key)
#   challenge  -> MODEL_ID=gemini/gemini-3.5-flash (fast) or gemini/gemini-3.5-pro
MODEL_ID = os.getenv("MODEL_ID") or "gpt-5.5"

CLI_RED = "\x1B[31m"
CLI_GREEN = "\x1B[32m"
CLI_CLR = "\x1B[0m"
CLI_BLUE = "\x1B[34m"


def main() -> None:
    task_filter = os.sys.argv[1:]
    results = []
    submit_result = None

    try:
        client = HarnessServiceClientSync(BITGN_URL)
        print("Connecting to BitGN", client.status(StatusRequest()))
        res = client.get_benchmark(GetBenchmarkRequest(benchmark_id=BENCH_ID))
        print(
            f"{EvalPolicy.Name(res.policy)} benchmark: {res.benchmark_id} "
            f"with {len(res.tasks)} tasks, model {MODEL_ID}.\n"
            f"{CLI_GREEN}{res.description}{CLI_CLR}"
        )

        run = client.start_run(
            StartRunRequest(
                name="@ai_nuts_and_bolts",
                benchmark_id=BENCH_ID,
                api_key=BITGN_API_KEY,
            )
        )

        try:
            for trial_id in run.trial_ids:
                trial = client.start_trial(
                    StartTrialRequest(trial_id=trial_id),
                )
                if task_filter and trial.task_id not in task_filter:
                    continue

                print(f"{'=' * 30} Starting task: {trial.task_id} {'=' * 30}")
                print(f"{CLI_BLUE}{trial.instruction}{CLI_CLR}\n{'-' * 80}")
                try:
                    run_agent(MODEL_ID, trial.harness_url, trial.instruction)
                except Exception as exc:
                    print(f"{CLI_RED}agent crashed: {exc}{CLI_CLR}")

                result = client.end_trial(EndTrialRequest(trial_id=trial.trial_id))
                score = result.score if result.score_available else None
                detail = list(result.score_detail) if result.score_available else []
                results.append((trial.task_id, score, detail, None, 0.0))
                if result.score_available:
                    style = CLI_GREEN if result.score == 1 else CLI_RED
                    explain = textwrap.indent("\n".join(result.score_detail), "  ")
                    print(
                        f"\n{style}Score: {result.score:0.2f}\n{explain}\n{CLI_CLR}"
                    )
                else:
                    print(f"\n{CLI_BLUE}Score: not available{CLI_CLR}\n")
        finally:
            submit_result = client.submit_run(SubmitRunRequest(run_id=run.run_id, force=True))

    except ConnectError as exc:
        print(f"{exc.code}: {exc.message}")
    except KeyboardInterrupt:
        print(f"{CLI_RED}Interrupted{CLI_CLR}")

    if submit_result is not None:
        results = merge_submit_scores(results, submit_result, task_filter=set(task_filter))
        if submit_score_available(submit_result):
            print(f"FINAL SCORE: {submit_result.score:0.2f}")

    scored = [
        (task_id, score)
        for task_id, score, _detail, err, _secs in results
        if err is None and isinstance(score, (int, float))
    ]
    if scored:
        for task_id, score in scored:
            style = CLI_GREEN if score == 1 else CLI_RED
            print(f"{task_id}: {style}{score:0.2f}{CLI_CLR}")

        total = sum(score for _, score in scored) / len(scored) * 100.0
        print(f"FINAL: {total:0.2f}%")


if __name__ == "__main__":
    main()
