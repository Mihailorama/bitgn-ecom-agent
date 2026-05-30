# 2026-05-30 Production Contest Start Memo

## Status

Docs-only state capture from the organizer memo immediately before the live
three-hour production contest. This file does not replace the accepted dev53
baseline:

- Accepted dev53 baseline remains `53.00/53` points, `53/53`, logs
  `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r9-t08-postfix11/`.
- The live production contour is expected to differ from dev53 and must be
  treated as a fresh task distribution.

## Organizer Signals

- The live contest is expected to have around `100` tasks.
- The platform now returns task scores as a batch after the whole run is closed.
  A run that is not submitted/closed does not produce useful scoring evidence.
- Rate limits are intended to slow brute-force agents. Normal LLM-agent usage
  guidance was described as roughly `15` runs per 30 minutes, with explicit
  `CodeResourceExhausted` / `Retry-After` responses when the limit is hit.
- Old task families and docs may vary by generated world. Discount caps,
  company facts, docs filenames, and policy values must be read from the live
  runtime, not from dev memory.
- Prompt injection can appear as a suffix on any task, not only on known
  security tasks.
- There are new OCR tasks and a new supply-chain/logistics rebalance family.
  Logistics answers may be evaluated by probabilistic simulation, so fractional
  scores can be expected even for reasonable plans.

## Contest Operating Plan

1. Run local gates only if they are cheap:
   `rtk uv run python -m py_compile agent.py llm.py run_mixed_parallel.py smoke_test.py`
   and `rtk uv run python smoke_test.py`.
2. Start with one live full sweep through `run_mixed_parallel.py`, close it, and
   parse the batch score.
3. Track rate-limit budget explicitly: platform runs, full sweeps, isolated
   probes, `Retry-After` waits, and remaining contest time.
4. Triage every live task from the first sweep. Do not assume old task ids keep
   their dev semantics; classify by observed instruction, tools, docs, and
   score details.
5. Security miss is the first fix priority and blocks leaderboard acceptance.
6. Otherwise choose the highest expected point gain per platform run and elapsed
   minute. New/simple tasks can outrank old regressions if they look cheap.
7. During the live contest, do not run 10 isolated samples by default:
   - use 1-2 for an obvious local bug;
   - use 3-5 for variant/flaky classification;
   - use 10 only for a high-value unclear miss if rate-limit budget allows.
8. Make one task-local fix at a time. Targeted passes are diagnostic only; a new
   accepted state requires a full sweep that is security-clean and improves or
   preserves the points/percent gate.

## Live Mixed Profile

Use the current dev53 speed/quality profile until live evidence says otherwise:

```bash
rtk env \
  SWEEP_LOG_DIR=artifacts/sweeps/<unique-live-label> \
  MIXED_PARALLEL=12 \
  MIXED_CLAUDE_LIMIT=6 \
  MIXED_CODEX_LIMIT=6 \
  CLAUDE_MODEL_ID=claude:opus \
  CODEX_MODEL_ID=codex:gpt-5.3-codex-spark \
  CODEX_REASONING_EFFORT=low \
  CODEX_VERBOSITY=low \
  MIN_ACCEPTED_PCT=98 \
  uv run python run_mixed_parallel.py
```

If Codex-route misses look like reasoning-depth misses, test `medium/low` only
on that task family before promoting it. Do not globally increase reasoning
effort during the contest without score/time evidence.
