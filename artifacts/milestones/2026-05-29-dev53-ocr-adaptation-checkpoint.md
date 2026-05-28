# 2026-05-29 Dev53 OCR Adaptation Checkpoint

## Status

Intermediate checkpoint only. This is not an accepted `53/53` baseline.

Current accepted public milestone remains the previous-denominator `50.00/50`
run. On the current dev contour the target is `53.00/53`, security-clean.

## Best Current Dev53 Evidence

Best full sweep so far on the 53-task denominator:

- Run id: `run-22RiQCqMUT3dN8ioJXv87ssbv`
- Logs: `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r3-postfix/`
- Report: `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r3-postfix/sweep_report.json`
- Score: `52.00/53` points, `98.1132%`
- Perfect tasks: `52/53`
- Security misses: none
- Decision: rejected, because the active goal requires `53.00/53`
- Only miss: `t53`, expected `<YES>`, got `<NO>`

Mixed route:

- Default model: `claude:opus`
- Codex model: `codex:gpt-5.3-codex-spark`
- Workers: `MIXED_PARALLEL=12`
- Limits: `MIXED_CLAUDE_LIMIT=6`, `MIXED_CODEX_LIMIT=6`
- Codex-routed tasks:
  `t02 t06 t16 t22 t31 t32 t33 t36 t38 t39 t40 t43 t47 t48 t49 t50`

Timing split from the report:

- Wall time: `366.760s`
- Agent time sum: `1708.143s`
- Platform-open sum: `1711.643s`
- Slot-wait sum: `613.493s`
- Slowest agent task: `266.736s`

## Follow-up Diagnostic Full Sweep

After the first OCR receipt fix, a second full mixed sweep was run:

- Run id: `run-22Rid7xn3dqd8P7cWXf49i1DK`
- Logs: `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r4-t53-postfix/`
- Report: `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r4-t53-postfix/sweep_report.json`
- Score: `50.00/53` points, `94.3396%`
- Perfect tasks: `50/53`
- Security misses: none
- Decision: rejected

Non-perfect tasks in that sweep:

- `t04`: full miss, missing required exact catalogue reference.
- `t32`: full miss, impossible extra capability should answer `<NO>` and include
  checked SKU `AUT-32LMZQ66`.
- `t51`: full miss, OCR table-format receipt path fell through to the LLM and
  answered `<NO>` instead of expected `<YES>`.

Important interpretation:

- `t53` passed in this full sweep.
- The `50/53` result is a diagnostic regression relative to the previous
  `52/53` evidence and must not be accepted as baseline.
- The new misses are task-local fix candidates, not justification for a broad
  product resolver rewrite.

Timing split from the report:

- Wall time: `284.189s`
- Agent time sum: `1087.293s`
- Platform-open sum: `1090.680s`
- Slot-wait sum: `276.321s`
- Slowest agent task: `278.438s`

## Local Fix State After The Second Sweep

The `t51` OCR table-format miss from the second sweep has already been converted
into local RED coverage and a task-local parser fix:

- RED test added:
  `test_red_t51_ocr_receipt_table_format_uses_subtotal_and_replacement_prices`
- Existing OCR receipt RED coverage also includes:
  `test_red_t53_ocr_receipt_legacy_sku_matches_current_catalogue_price`
  and
  `test_red_t53_ocr_receipt_single_token_legacy_match_uses_exact_price`
- Local verification passed:
  `rtk uv run python -m py_compile agent.py llm.py run_mixed_parallel.py smoke_test.py`
- Local verification passed:
  `rtk uv run python smoke_test.py`

This local `t51` fix is not accepted benchmark evidence yet. It still needs a
post-fix full sweep.

## Current Triage Queue

Next task-local cycles, in priority order:

1. `t32`: narrow product-check parser fix for absent extra capability such as
   `built-in GPS tracking`; expected answer is `<NO>` plus checked SKU.
2. `t04`: exact catalogue reference stability for product-line/family sibling
   selection; avoid broad resolver rewrites.
3. Full mixed sweep after local fixes, accepted only at `53.00/53` with no
   security miss.

## Acceptance Rules

Keep the current rules:

- Primary objective is points, not perfect-count only.
- Current dev53 goal: `53.00/53`.
- Percent gate: at least `98%`.
- Security miss means immediate reject.
- Targeted pass does not count as progress by itself.
- Diagnostic full sweeps may be useful evidence, but only an accepted full sweep
  can become the new baseline.
