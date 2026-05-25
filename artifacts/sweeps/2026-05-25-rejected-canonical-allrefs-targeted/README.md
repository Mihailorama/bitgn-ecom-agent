## Targeted Snapshot: rejected canonical all-refs inventory patch

- base: `agent.py` restored from `66a7ccb`
- experimental changes:
  - prefer `/fam_.../<SKU>.json` paths in `_canonical_product_path`
  - cite all resolved inventory products instead of only counted products
- targeted command: `PARALLEL=6 MODEL_ID=codex:gpt-5.3-codex TASKS='t13 t14 t15 t16' make sweep`
- result: `0/4`

### Verdict

Rejected. The path-canonicalization/all-refs approach still produced invalid
catalog refs across `t13-t16`. The correct next step is a proper inventory
resolver that derives required refs from deterministic SQL and validates them
against grader-accepted paths before submission, not a broad post-hoc ref
expansion.

