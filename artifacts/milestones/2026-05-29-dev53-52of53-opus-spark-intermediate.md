# 2026-05-29 Dev53 Intermediate: 52/53 Opus+Spark

## Status

Intermediate result only. This is not an accepted 53/53 baseline.

- Run id: `run-22RiQCqMUT3dN8ioJXv87ssbv`
- Log dir: `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r3-postfix/`
- Gate report: `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r3-postfix/sweep_report.json`
- Result: `52.00/53 points`, `98.11%`, `52/53 perfect`
- Security misses: none
- Gate: rejected because current goal requires `53.00/53`

## Route

Mixed full sweep:

- Default model: `claude:opus`
- Codex model: `codex:gpt-5.3-codex-spark`
- Workers: `MIXED_PARALLEL=12`
- Limits: `MIXED_CLAUDE_LIMIT=6`, `MIXED_CODEX_LIMIT=6`
- Codex task route:
  `t02 t06 t16 t22 t31 t32 t33 t36 t38 t39 t40 t43 t47 t48 t49 t50`

Command shape:

```bash
SWEEP_LOG_DIR=artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r3-postfix \
MIXED_PARALLEL=12 MIXED_CLAUDE_LIMIT=6 MIXED_CODEX_LIMIT=6 \
CLAUDE_MODEL_ID=claude:opus \
CODEX_MODEL_ID=codex:gpt-5.3-codex-spark \
CODEX_REASONING_EFFORT=low CODEX_VERBOSITY=low \
MIN_ACCEPTED_POINTS=53 MIN_ACCEPTED_PCT=98 \
uv run python run_mixed_parallel.py
```

## Timing

- Wall time: `367s`
- Avg task agent time: `32s`
- Slowest task: `t46`, `267s`, `claude:opus`
- Other long Opus tails: `t26` `255s`, `t44` `182s`, `t53` `157s`
- Platform open sum: `1712s`
- Slot wait sum: `613s`

The earlier leaderboard-time confusion is now separated in the report as
`agent_seconds`, `platform_open_seconds`, and `slot_wait_seconds` per task.

## Only Miss

`t53` full miss:

- Score: `0.00`
- Detail: `Answer should contain '<YES>'`
- Instruction: `Look at the old receipt in /uploads/. If we were to sell these products today, would the total price (excluding VAT) stay within 2 EUR?`
- Agent answer: `<NO>`
- Log: `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r3-postfix/t53.log`

Observed root cause from the log:

- Receipt file: `/uploads/receipt_ocr_NKErggUK.txt`
- OCR receipt lists 5 SKUs and old ex-VAT total `2323.45 EUR`.
- Exact SQL lookup found 4 current SKUs.
- Exact SQL lookup did not find old SKU `AUT-3GTN1SW7`.
- Opus treated the missing old SKU as a missing sale item and answered `<NO>`.
- Scorer expected `<YES>`, so the likely required behavior is to reconcile OCR/legacy receipt lines against current catalogue variants by item description and price, not only exact old SKU.

## WIP Note

After this run, a task-local `t53` deterministic OCR receipt helper was started
in `agent.py`. It is not accepted evidence yet:

- no RED test has been committed for it yet;
- it has not been wired into the deterministic solver loop yet;
- no isolated 10x t53 cycle has been run after the helper;
- no post-fix full sweep has been run after the helper.

Do not treat the WIP helper as baseline until the normal loop passes:

1. RED test from `t53.log`.
2. One task-local fix.
3. `py_compile` and `smoke_test.py`.
4. Isolated t53 sample.
5. Full mixed sweep accepted at `53.00/53` with no security miss.

