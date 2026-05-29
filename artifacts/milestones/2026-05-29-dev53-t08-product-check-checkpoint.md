# 2026-05-29 Dev53 T08 Product-Check Checkpoint

## Status

Intermediate checkpoint only. This is not a new accepted baseline.

Active target remains:

- `53.00/53` points
- at least `98%`
- no security misses

## Best Current Full-Sweep Evidence

Latest full mixed sweep evidence:

- Logs: `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r8-r7misses-postfix/`
- Report:
  `artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r8-r7misses-postfix/sweep_report.json`
- Model mix: `claude:opus` + `codex:gpt-5.3-codex-spark`
- Workers: `12` total, `6` Claude slots, `6` Codex slots
- Points: `51.9965/53`
- Gate-rounded points: `52.00/53`
- Score percent: `98.1066%`
- Perfect tasks: `51/53`
- Wall time: `155.408s`
- Security misses: none
- Decision: rejected because the active goal requires `53.00/53`

Non-perfect tasks in that sweep:

- `t08`: full miss, missing required catalogue reference
  `/proc/catalog/cleaning/cloths_mops_wipes/fam_cleaning_cloths_mops_wipes_0020_3vpodlpd/CLN-TXOFANPK.json`
- `t48`: partial, fraud/archive amount mismatch with false-positive payment refs

## Current T08 Local Fix State

The current working tree contains three narrow `t08` product-check fixes with
RED coverage:

- Variant properties stored as a JSON blob on the product row are parsed and
  merged into SQL candidates.
- Line/model hint matching accepts compact forms such as `1V4-H6H` vs
  `1V4 H6H`.
- Size matching treats prompt aliases such as `3XL` as equivalent to catalogue
  codes such as `XXXL`.

Smoke coverage added:

- `test_red_t08_product_check_reads_variant_properties_blob_sibling`
- `test_red_t08_product_check_sql_dashless_model_sibling_is_checked`
- `test_red_t08_product_check_size_3xl_matches_xxxl_sibling`

Diagnostic support added:

- Set `PRODUCT_CHECK_DIAG=1` to print a compact `PRODUCT_CHECK_DIAG` JSON line
  from the deterministic product-check resolver.
- The diagnostic includes selected spec fields, candidate count, line/hint
  matches, product property keys, and base/full property matches.

## Live T08 Evidence After Local Fixes

The local fixes are not accepted yet. Live isolated `t08` runs still failed:

- `artifacts/sweeps/2026-05-29-dev53-t08-postfix8-r72/`
  - Required ref:
    `/proc/catalog/adhesives_sealants/sealants/fam_adhesives_sealants_sealants_0009_1giszqpo/ADH-2DPPU38B.json`
  - Agent cited:
    `/proc/catalog/adhesives_sealants/sealants/fam_adhesives_sealants_sealants_0009_1giszqpo/ADH-1M5XCAHE.json`
- `artifacts/sweeps/2026-05-29-dev53-t08-postfix8-r73/`
  - Required ref:
    `/proc/catalog/workwear/work_trousers/fam_workwear_work_trousers_0008_3stg95kk/WRK-63JUIPZW.json`
  - Agent cited:
    `/proc/catalog/workwear/work_trousers/fam_workwear_work_trousers_0008_3stg95kk/WRK-1GH1A91T.json`
- `artifacts/sweeps/2026-05-29-dev53-t08-postfix8-r74/`
  - Required ref:
    `/proc/catalog/garden_tools/trimmers_blowers/fam_garden_tools_trimmers_blowers_0004_fagckfxr/GRD-MDGA48I7.json`
  - Agent cited:
    `/proc/catalog/garden_tools/trimmers_blowers/fam_garden_tools_trimmers_blowers_0004_fagckfxr/GRD-1IZWSKRN.json`

Interpretation:

- The three fixes are locally valid but do not close the live `t08` family.
- This is no longer safe to keep patching as one-off product-property cases.
- Next action should be diagnostic evidence, not another blind resolver patch.

## Local Verification

Local gate at checkpoint:

```bash
rtk uv run python -m py_compile agent.py llm.py run_mixed_parallel.py smoke_test.py
rtk uv run python smoke_test.py
```

Both commands pass.

## Next Action

Run one isolated diagnostic `t08` with `PRODUCT_CHECK_DIAG=1`:

```bash
rtk env SWEEP_LOG_DIR=artifacts/sweeps/2026-05-29-dev53-t08-diag-r75 \
  PRODUCT_CHECK_DIAG=1 \
  MIXED_PARALLEL=1 MIXED_CLAUDE_LIMIT=1 MIXED_CODEX_LIMIT=1 \
  CLAUDE_MODEL_ID=claude:opus \
  CODEX_MODEL_ID=codex:gpt-5.3-codex-spark \
  CODEX_REASONING_EFFORT=low CODEX_VERBOSITY=low \
  MIN_ACCEPTED_POINTS=1 MIN_ACCEPTED_PCT=98 \
  uv run python run_mixed_parallel.py t08
```

Classify the diagnostic before changing code again:

- required SKU absent from candidate list: fix candidate discovery;
- required SKU present but base props do not match: fix parser/matcher only if
  the issue is narrow and covered by a RED test;
- required SKU present and matching but not cited: fix selection/dedupe logic;
- repeated broad sibling ambiguity: redesign the `t08` product-check resolver or
  route `t08` away from the current deterministic path.

Do not run a full sweep from this checkpoint until `t08` has live diagnostic
evidence or the user explicitly overrides.
