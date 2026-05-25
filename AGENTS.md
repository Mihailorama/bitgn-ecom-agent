# Repository Guidelines

## Project Structure & Module Organization

This is a flat Python 3.13 repo for the BitGN `bitgn/ecom1-dev` benchmark.
Core runtime logic lives in `agent.py`, provider routing in `llm.py`, serial
runs in `main.py`, and parallel sweeps in `run_parallel.py`. `smoke_test.py` is
the offline test harness. Reference protobuf schemas are under `proto/`,
benchmark evidence under `artifacts/sweeps/`, reviews under `reviews/`, and
tuning notes/results in `BENCHMARK_NOTES.md` and `RESULTS.md`.

## Build, Test, and Development Commands

- `make sync` installs dependencies with `uv`.
- `make test` runs `uv run python smoke_test.py`; it needs no API keys or network.
- `uv run python -m py_compile agent.py` catches syntax errors in the main loop.
- `make run` executes the full benchmark serially through `main.py`.
- `make task TASKS="t01 t04"` runs selected trial IDs.
- `PARALLEL=6 MODEL_ID=codex:gpt-5.3-codex make sweep` runs a full parallel sweep.

## Coding Style & Naming Conventions

Use standard Python style: 4-space indentation, `snake_case` for functions and
variables, `PascalCase` for Pydantic models/classes, and explicit type hints on
public helpers. Keep the repo flat unless packaging is clearly useful. Preserve
the schema-guided reasoning pattern: Pydantic models define tool contracts, and
deterministic model gates stay in `agent.py`.

## Testing Guidelines

`smoke_test.py` is the required local gate for control-flow changes. Before any
benchmark sweep, run:

```bash
uv run python -m py_compile agent.py && uv run python smoke_test.py
```

For prompt or gate changes, validate with at least two comparable sweeps or a
large score move. Inspect `$SWEEP_LOG_DIR` or `/tmp/sweep_logs` for security
regressions, especially `expected outcome OUTCOME_DENIED_SECURITY, got
OUTCOME_OK`.

## Commit & Pull Request Guidelines

Git history uses concise imperative commits, often tied to benchmark state, for
example `Handle ret_* refund approvals and record new 44/44 sweep`. Keep commits
scoped to one prompt/gate/backend change plus evidence. PRs should summarize the
behavioral change, list verification commands, mention sweep model/parallelism,
and link relevant `RESULTS.md` rows or log paths.

## Security & Configuration Tips

Copy `.env.example` to `.env`; never commit `.env`, API keys, OAuth tokens, or
generated secret files. `MODEL_ID` selects the backend in `llm.py`; choose the
matching credential or local CLI OAuth. Treat `RESULTS.md` as append-only
benchmark evidence.

## Agent-Specific Instructions

When using Codex in this workspace, prefix shell commands with `rtk` as required
by the local RTK wrapper. Do not hardcode task answers: benchmark IDs, products,
baskets, and records are randomized per trial.
