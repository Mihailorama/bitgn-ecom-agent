# 2026-05-29 Dev53 Localfix Intermediate Checkpoint

## Status

Intermediate checkpoint only. This is not a new accepted baseline.

The active target on the current dev contour is still:

- `53.00/53` points
- at least `98%`
- no security misses

The previous accepted public milestone remains the `50.00/50` result on the
older denominator. For the current 53-task denominator, the best confirmed full
sweep evidence is still `52.00/53`.

## Best Current Full-Sweep Evidence

Best current dev53 full sweep:

- Logs: `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r3-postfix/`
- Report:
  `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r3-postfix/sweep_report.json`
- Model mix: `claude:opus` + `codex:gpt-5.3-codex-spark`
- Workers: `12` total, `6` Claude slots, `6` Codex slots
- Score: `52.00/53`, `98.1132%`
- Security misses: none
- Decision: rejected only because the active goal requires `53.00/53`
- Only miss in that sweep: `t53`

Follow-up diagnostic full sweep after the first OCR fix:

- Logs:
  `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r4-t53-postfix/`
- Report:
  `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r4-t53-postfix/sweep_report.json`
- Score: `50.00/53`, `94.3396%`
- Security misses: none
- Decision: rejected
- Non-perfect tasks: `t04`, `t32`, `t51`
- Important: `t53` passed in this run

## Current Local Fix State

The `r4` misses have been converted into local RED coverage and narrow fixes.

### t04

Problem family:

- Product-check task answered `<YES>` but cited only one exact catalogue
  candidate.
- Scorer required another exact same-line/same-property candidate reference.

Local fix:

- `_try_product_check` now keeps all exact SQL candidates for YES references
  while still using one selected product for the answer text.
- No broad resolver rewrite.

Coverage:

- `test_red_t04_product_check_cites_all_exact_yes_candidates`

### t32

Problem families:

- Extra capability such as `built-in GPS tracking` was not parsed as a product
  property, so an impossible support-note claim could incorrectly pass.
- Same-family JSON sibling could be skipped when numeric JSON values were
  represented as floats such as `1500.0`.

Local fixes:

- Product property parser recognizes `gps tracking`.
- `built-in GPS tracking` normalizes to `gps tracking yes`.
- Numeric property matching treats integer and float textual forms as equal
  when their numeric values match.

Coverage:

- `test_red_t32_product_check_gps_tracking_absent_returns_no_with_checked_sku`
- `test_red_t32_product_check_family_json_numeric_float_sibling_is_checked`

### t51

Problem families:

- OCR receipt table-format path could miss subtotal/current-price replacement
  cases.
- Unreadable OCR descriptions could leave a legacy SKU unresolved even when a
  unique near-exact current catalogue price closes the receipt total.

Local fixes:

- Receipt OCR solver handles table subtotal/current-price replacement cases.
- Price fallback can use one unique near-exact current price candidate.
- Candidate scoring no longer prevents a valid zero-token/price-only fallback
  from being selected.

Coverage:

- `test_red_t51_ocr_receipt_table_format_uses_subtotal_and_replacement_prices`
- `test_red_t51_ocr_receipt_unique_price_fallback_handles_unreadable_description`

## Verification

Local gates currently pass:

```bash
rtk uv run python -m py_compile agent.py llm.py run_mixed_parallel.py smoke_test.py
rtk uv run python smoke_test.py
```

The latest live related subset before the final t32 numeric fix was:

- Logs: `artifacts/sweeps/2026-05-29-dev53-localfix-related-r2/`
- Score: `3.00/4`
- Passed: `t04`, `t51`, `t53`
- Failed: `t32`
- Security misses: none

That subset failure is covered by the local t32 numeric-family fix above. It
still needs live confirmation.

## Next Gate

Next action should be a live related subset, not a broad rewrite:

```bash
rtk env SWEEP_LOG_DIR=artifacts/sweeps/2026-05-29-dev53-localfix-related-r3 \
  MIXED_PARALLEL=4 MIXED_CLAUDE_LIMIT=2 MIXED_CODEX_LIMIT=2 \
  CLAUDE_MODEL_ID=claude:opus \
  CODEX_MODEL_ID=codex:gpt-5.3-codex-spark \
  CODEX_REASONING_EFFORT=low CODEX_VERBOSITY=low \
  MIN_ACCEPTED_POINTS=4 MIN_ACCEPTED_PCT=98 \
  uv run python run_mixed_parallel.py t04 t32 t51 t53
```

If that subset is `4.00/4` and security-clean, run a full mixed sweep:

```bash
rtk env SWEEP_LOG_DIR=artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r5-localfix \
  MIXED_PARALLEL=12 MIXED_CLAUDE_LIMIT=6 MIXED_CODEX_LIMIT=6 \
  CLAUDE_MODEL_ID=claude:opus \
  CODEX_MODEL_ID=codex:gpt-5.3-codex-spark \
  CODEX_REASONING_EFFORT=low CODEX_VERBOSITY=low \
  MIN_ACCEPTED_POINTS=53 MIN_ACCEPTED_PCT=98 \
  LEADERBOARD_BEST_POINTS=50 LEADERBOARD_BEST_MAX_POINTS=50 \
  LEADERBOARD_BEST_SECONDS=3603 \
  uv run python run_mixed_parallel.py
```

Accept only if:

- points are `53.00/53`
- percent is at least `98%`
- security misses are empty

If the sweep is below `53.00/53`, treat it as diagnostic evidence and triage the
highest-cost non-perfect task first.
