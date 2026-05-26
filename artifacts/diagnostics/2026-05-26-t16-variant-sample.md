# t16 Variant Sample After Exact-Candidate Patch

Date: 2026-05-26
Profile: `MODEL_ID=codex:gpt-5.3-codex`, `PARALLEL=1`, `TASKS=t16`
Code state: saved exact-candidate `ge` inventory path plus `fit` parser split;
diagnostic candidate, not accepted as a scoring milestone

## Commands

```sh
for i in 01 02 03 04 05 06 07 08 09 10; do
  SWEEP_LOG_DIR="artifacts/sweeps/2026-05-26-t16-variant-sample-r${i}" \
    PARALLEL=1 MODEL_ID=codex:gpt-5.3-codex TASKS='t16' make sweep
done
```

The harness reported `bitgn/ecom1-dev: 48 tasks` during these subset runs. The
immediately preceding full sweep still reported 47 scored tasks and landed at
`46/47`; treat the benchmark task-count drift as live external state.

## Results

| run | score | agent answer | grader detail | selected product refs |
|---|---:|---|---|---|
| full `2026-05-26-t16-exact-candidate-full-codex53` | 0 | not repeated here | missing `/proc/catalog/automotive/engine_oil/fam_automotive_engine_oil_0013_3ph4ges4/AUT-3OQ0L7I7.json` | see log |
| r01 | 0 | `count : 4` | expected `count : 3` | valve, lawn mower, work trousers, shelving |
| r02 | 0 | `<COUNT:1>` | missing `/proc/catalog/adhesives_sealants/adhesives_glues/fam_adhesives_sealants_adhesives_glues_0008_2qkhz1sk/ADH-SXB3F38I.json` | cleaning liquid |
| r03 | 1 | `count : 3` | pass | storage bin, cordless saw/sander, drain trap |
| r04 | 0 | `<COUNT:1>` | missing `/proc/catalog/storage/shelving_cabinets/fam_storage_shelving_cabinets_0009_276xr5q6/STO-3JGPJ1R7.json` | safety eyewear |
| r05 | 0 | `<COUNT:1>` | missing `/proc/catalog/safety_gear/safety_eyewear/fam_safety_gear_safety_eyewear_0005_2f7zzwhp/SFE-3UUD3O1T.json` | automotive cleaner |
| r06 | 1 | `2` | pass | safety eyewear, drain trap |
| r07 | 1 | `<COUNT:3>` | pass | lawn mower, fastener, cordless saw/sander |
| r08 | 0 | `1` | expected `0` | lawn mower |
| r09 | 0 | `<COUNT:2>` | missing `/proc/catalog/cleaning/cloths_mops_wipes/fam_cleaning_cloths_mops_wipes_0008_2q5qu6wc/CLN-S2FHUNC7.json` | work top, workshop machine |
| r10 | 0 | `count : 2` | missing `/proc/catalog/electrical/led_bulbs/fam_electrical_led_bulbs_0011_7ft9sg7i/ELC-2REZIVXN.json` | lawn mower, screwdriver/hex set |

Security grep was clean:

```sh
rg -n "expected outcome OUTCOME_DENIED_SECURITY, got OUTCOME_OK" \
  artifacts/sweeps/2026-05-26-t16-variant-sample-r*/t16.log \
  artifacts/sweeps/2026-05-26-t16-exact-candidate-full-codex53/*.log
```

## Pattern

The current exact-candidate patch is not stable enough to commit as a scoring
fix. It can close a seed (`targeted-r3`, sample r03/r06/r07), but the 10-run
sample passed only 3/10 and the full sweep stayed at `46/47`.

The common failure is not one missing property alias. Every sampled run used the
deterministic `_try_inventory_count` path and the new `exact candidate SQL`
reason, but failures split into:

- numeric false positives: r01 and r08 counted a product that the grader did not
  count;
- wrong sibling refs with apparently matching numeric answer: full, r02, r04,
  r05, r09, r10 selected a different qualifying product ref than the required
  one.

This matches the older diagnostic conclusion in `BENCHMARK_NOTES.md`: SQL-only
`products` / `product_properties` candidate selection is not a complete variant
resolver for dense `t16` prompts. Required refs can be sibling JSON records under
the same catalogue family directory, and the code needs a resolver that records
candidate groups and reason codes before applying the inventory ref policy.

## Next Single Change Recommendation

Do not stack more ad-hoc aliases onto `_PROP_PREFIXES` as the next scoring fix.
The next isolated change should be a typed resolver refactor, covered by tests
before behavior expansion:

1. Extract `resolve_product_variant(vm, spec)` returning `{status, candidates,
   reason, diagnostics}`.
2. Extract `build_inventory_refs(groups, inventory, threshold, op)` so count and
   refs are tested independently.
3. Add diagnostic records per requested product: parsed props, SQL candidates,
   family JSON siblings inspected, inventory rows, chosen SKU/ref, reason.
4. Only after that, add the behavior expansion: augment SQL candidates with
   listed/read JSON siblings from candidate `family_id` directories before
   declaring a product exact, ambiguous, or fallback-only.

Acceptance should be stricter than one targeted pass: at least `8/10` t16
sample pass rate, then the normal inventory subset, then full sweep.
