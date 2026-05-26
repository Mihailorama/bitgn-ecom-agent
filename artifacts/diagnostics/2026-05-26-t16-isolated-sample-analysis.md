# t16 isolated sample analysis (2026-05-26)

## Setup

- branch: `main` at commit `7c0c79b`
- model: `codex:gpt-5.3-codex`
- command shape: `SWEEP_LOG_DIR=<run_dir> PARALLEL=1 uv run python run_parallel.py t16`
- runs: `r01..r10`
- logs:
  - `artifacts/sweeps/2026-05-26-t16-isolated-sample-r01/t16.log`
  - `artifacts/sweeps/2026-05-26-t16-isolated-sample-r02/t16.log`
  - `artifacts/sweeps/2026-05-26-t16-isolated-sample-r03/t16.log`
  - `artifacts/sweeps/2026-05-26-t16-isolated-sample-r04/t16.log`
  - `artifacts/sweeps/2026-05-26-t16-isolated-sample-r05/t16.log`
  - `artifacts/sweeps/2026-05-26-t16-isolated-sample-r06/t16.log`
  - `artifacts/sweeps/2026-05-26-t16-isolated-sample-r07/t16.log`
  - `artifacts/sweeps/2026-05-26-t16-isolated-sample-r08/t16.log`
  - `artifacts/sweeps/2026-05-26-t16-isolated-sample-r09/t16.log`
  - `artifacts/sweeps/2026-05-26-t16-isolated-sample-r10/t16.log`

## Result

- pass rate: `1/10`
- fails: `9/10`
- dominant failure class: missing required `/proc/catalog/...json` reference

## Per-run scoreboard

| Run | Score | Grader feedback |
|---|---:|---|
| r01 | 0.00 | answer missing required reference `/proc/catalog/plumbing/drain_traps_siphons/fam_plumbing_drain_traps_siphons_0017_1e8dyy1h/PLB-89OIMQ7V.json` |
| r02 | 0.00 | answer missing required reference `/proc/catalog/paints_finishes/wall_paint/fam_paints_finishes_wall_paint_0001_1fxyeshg/PNT-2ZIDOST2.json` |
| r03 | 0.00 | answer missing required reference `/proc/catalog/fasteners/anchors_plugs/fam_fasteners_anchors_plugs_0005_2zk0jjxf/FST-38SY5B0L.json` |
| r04 | 0.00 | Answer should be `"count : 3"` |
| r05 | 0.00 | answer missing required reference `/proc/catalog/hand_tools/pliers_wrenches/fam_hand_tools_pliers_wrenches_0010_1de69d8p/HND-B6M82SLI.json` |
| r06 | 0.00 | Answer should be `"[QTY:2]"` |
| r07 | 0.00 | answer missing required reference `/proc/catalog/safety_gear/safety_eyewear/fam_safety_gear_safety_eyewear_0019_3fek5qpw/SFE-A7UPF22F.json` |
| r08 | 0.00 | answer missing required reference `/proc/catalog/electrical/led_bulbs/fam_electrical_led_bulbs_0003_2xf76vmg/ELC-YZILNRDC.json` |
| r09 | 0.00 | answer missing required reference `/proc/catalog/plumbing/pipe_fittings/fam_plumbing_pipe_fittings_0001_9b237m89/PLB-IKJ3ZRWF.json` |
| r10 | 1.00 | pass |

## Inventory-diagnostic pattern

- every run used deterministic path: `_try_inventory_count`
- each run had `6` requested products and `6` `INVENTORY_DIAG` records
- pass run (`r10`) had `status="exact"` for all 6 products
- most fail runs mix `exact_group` and `fallback_single`, with missing required ref typically tied to one `fallback_single` item in the same family directory where the grader expects another sibling SKU
- two count-mismatch runs (`r04`, `r06`) still exhibit mixed exact/fallback diagnostics, consistent with wrong sibling selection affecting both count and refs

Quick counts from logs:

| Run | fallback | exact | positive candidates |
|---|---:|---:|---:|
| r01 | 4 | 2 | 1 |
| r02 | 4 | 2 | 0 |
| r03 | 2 | 4 | 2 |
| r04 | 1 | 5 | 4 |
| r05 | 3 | 3 | 3 |
| r06 | 4 | 2 | 3 |
| r07 | 3 | 3 | 1 |
| r08 | 2 | 4 | 3 |
| r09 | 2 | 4 | 3 |
| r10 | 0 | 6 | 1 |

## Implications for next isolated fix

1. Primary root-cause candidate is resolver behavior for `fallback_single` items in t16 inventory counting: it often cites/counts one sibling SKU while grader expects another sibling in the same family.
2. Next code step should remain task-local:
   - add RED tests only from this t16 sample set (at least one missing-ref case and one count-mismatch case);
   - modify only t16 deterministic branch behavior;
   - keep `t13/t14/t15/t45/t47` as mandatory no-regression set before any full sweep.
3. Reject criteria remains strict: if full sweep solved-task count drops, the change is reverted even if t16 sample improves.
