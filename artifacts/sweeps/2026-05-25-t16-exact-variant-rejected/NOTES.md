# t16 Exact-Variant Branch Rejected Experiment

Date: 2026-05-25

Goal: isolate the recurring `t16` inventory/count miss into a semantic
high-density exact-variant branch, without task-id hardcoding, so future hidden
runs with more than 44 tasks can route the same class safely.

Root cause observed:
- The old deterministic inventory resolver falls back from exact property match
  to a similar SKU when no full variant match is found.
- In `t16`-class prompts this creates wrong-SKU grounding and missing required
  product refs, especially for dense six-product store inventory lists.
- A parser gap also contributed: labels such as `tank volume`, `grip type`, and
  `fit` were not recognized in the WIP branch.

WIP attempted:
- Add strict full-match extraction for dense single-store inventory prompts.
- Treat unresolved exact variants as unavailable instead of falling back to a
  partial SKU.
- Group indistinguishable exact SKUs so the count is per requested product, not
  per sibling SKU.
- Experiment with refs as available-only, all exact, then exact refs only for
  available groups.

Validation result:
- Targeted `t13-t16` could pass (`sweep_exact_variant_t13_t16_v4`,
  `sweep_exact_variant_t13_t16_v5`), but it was not stable.
- Full sweeps rejected the branch:
  - `sweep_exact_variant_full`: `42/44`, misses `t15`, `t16` via invalid refs.
  - `sweep_exact_variant_full2`: `41/44`, misses `t05`, `t06`, `t16`; t05/t06
    were unrelated model variance after this WIP, while t16 still missed a
    required storage product ref.
- Security grep was clean for both full sweeps.

Decision:
- Runtime code was reverted after saving `wip.diff`; do not land this exact
  branch as-is.
- Next attempt should be a real resolver refactor: structured
  `resolve_product_variant()` returning candidate groups with reason codes,
  plus fixture tests from these saved logs before another full sweep.

