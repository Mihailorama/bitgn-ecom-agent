# Sweep State Snapshot (2026-05-25)

Saved from `/tmp/sweep_logs` into git for reproducible debugging and handoff.

## Contents

- `t01.log` ... `t44.log`: per-task traces captured from the current local sweep-log directory.
- This snapshot is intended for investigation of variant grounding failures and
  deterministic-vs-LLM routing decisions.

## Relevant run context

- Model profile: `MODEL_ID=codex:gpt-5.3-codex`
- Main quality profile: `PARALLEL=6`
- Validation gate used before sweeps:
  - `uv run python -m py_compile agent.py llm.py`
  - `uv run python smoke_test.py`

## Key observed outcomes around this snapshot

- Full sweep (from `RESULTS.md`, 2026-05-25 18:45):
  - `97.7%` (`43/44`), `wall 174s`, `avg/task 21s`
  - Notable miss: `t36` required `/docs/checkout.md` grounding.
- Full sweep (from `RESULTS.md`, 2026-05-25 18:51):
  - `97.7%` (`43/44`), `wall 224s`, `avg/task 26s`
  - Notable miss: `t16` required product reference mismatch.

## Current hypotheses for follow-up

1. `t13-t16` failures are mostly grounding-reference selection issues, not
   arithmetic mistakes.
2. Aggressive deterministic shortcuts improve speed but often lower recall of
   required SKU references on seed-variant prompts.
3. Safer path is helper-level refactor and targeted tests before re-expanding
   deterministic coverage.

## Next commands for reproducible follow-up

```bash
PARALLEL=6 MODEL_ID=codex:gpt-5.3-codex make sweep
rg "expected outcome OUTCOME_DENIED_SECURITY, got OUTCOME_OK" /tmp/sweep_logs/*.log
PARALLEL=2 MODEL_ID=codex:gpt-5.3-codex uv run python run_parallel.py t13 t14 t15 t16
```
