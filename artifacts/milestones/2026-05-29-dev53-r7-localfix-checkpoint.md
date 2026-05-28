# 2026-05-29 Dev53 r7 Localfix Checkpoint

## Status

Intermediate checkpoint only. This is not an accepted `53/53` baseline.

Active target remains:

- `53.00/53` points on the current dev53 contour
- score percent at least `98%`
- no security misses

## Best Confirmed Evidence

Best full sweep so far:

- Logs: `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r3-postfix/`
- Report:
  `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r3-postfix/sweep_report.json`
- Model mix: `claude:opus` + `codex:gpt-5.3-codex-spark`
- Workers: `MIXED_PARALLEL=12`, Claude limit `6`, Codex limit `6`
- Score: `52.00/53`, `98.1132%`
- Security misses: none
- Decision: rejected only because the active goal requires `53.00/53`
- Timing: `366.760s` wall, `1708.143s` agent sum,
  `1711.643s` platform-open sum, `613.493s` slot-wait sum

## Latest Full Sweep

Latest full sweep after `t07` and `t42` local fixes:

- Logs:
  `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r7-t07-t42-postfix/`
- Report:
  `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r7-t07-t42-postfix/sweep_report.json`
- Run id: `run-22RixeNnxogeKMPQGJKrZr7pR`
- Score: `48.00/53`, `90.5660%`
- Security misses: none
- Decision: rejected
- Timing: `249.752s` wall, `1137.348s` agent sum,
  `1143.330s` platform-open sum, `532.396s` slot-wait sum

The fixed tasks from the previous cycle held in this sweep:

- `t07`: passed
- `t42`: passed

New non-perfect tasks in r7:

- `t02`: expected `<YES>` for catalogue product check.
- `t30`: missing required reference `/docs/payments/3ds.md`.
- `t32`: missing required current catalogue family JSON reference.
- `t43`: expected `OUTCOME_NONE_UNSUPPORTED`, got `OUTCOME_OK`.
- `t46`: expected `OUTCOME_OK`, got `OUTCOME_ERR_INTERNAL`.

## Local Fixes Now Present

The r7 misses have local RED coverage and task-local fixes:

- `t02`: product property parsing handles `lens_colour` alias and strips trailing
  `is` from parsed values.
- `t30`: 3-D Secure trigger recognizes `3-DS` and cites
  `/docs/payments/3ds.md` on cross-customer denial.
- `t32`: current-schema family JSON parsing supports current field names and
  list properties; product check recognizes `voice control`.
- `t43`: refund amount parsing handles euro-symbol forms such as `€ 254` so
  amount-only refund requests stay unsupported.
- `t46`: current-schema discount path can resolve the latest checkoutable basket
  by customer email from the employee's store.

Local verification passed after these fixes:

```bash
rtk uv run python -m py_compile agent.py llm.py run_mixed_parallel.py smoke_test.py
rtk uv run python smoke_test.py
```

This is local evidence only. It still needs live subset confirmation.

## Next Gate

Run the related subset first:

```bash
rtk env SWEEP_LOG_DIR=artifacts/sweeps/2026-05-29-dev53-r7-misses-postfix-r01 \
  MIXED_PARALLEL=5 MIXED_CLAUDE_LIMIT=3 MIXED_CODEX_LIMIT=3 \
  CLAUDE_MODEL_ID=claude:opus \
  CODEX_MODEL_ID=codex:gpt-5.3-codex-spark \
  CODEX_REASONING_EFFORT=low CODEX_VERBOSITY=low \
  MIN_ACCEPTED_POINTS=5 MIN_ACCEPTED_PCT=98 \
  uv run python run_mixed_parallel.py t02 t30 t32 t43 t46
```

If the subset is `5.00/5` and security-clean, run the next full sweep:

```bash
rtk env SWEEP_LOG_DIR=artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r8-r7misses-postfix \
  MIXED_PARALLEL=12 MIXED_CLAUDE_LIMIT=6 MIXED_CODEX_LIMIT=6 \
  CLAUDE_MODEL_ID=claude:opus \
  CODEX_MODEL_ID=codex:gpt-5.3-codex-spark \
  CODEX_REASONING_EFFORT=low CODEX_VERBOSITY=low \
  MIN_ACCEPTED_POINTS=53 MIN_ACCEPTED_PCT=98 \
  LEADERBOARD_BEST_POINTS=50 LEADERBOARD_BEST_MAX_POINTS=50 \
  LEADERBOARD_BEST_SECONDS=3603 \
  uv run python run_mixed_parallel.py
```

Accept only if the full sweep is `53.00/53`, at least `98%`, and
security-clean. Otherwise treat it as diagnostic evidence and triage the largest
remaining loss first.
