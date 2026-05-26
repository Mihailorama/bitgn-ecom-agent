# 2026-05-26 Exact Group Plus Color Full Sweep

Command:

```bash
PARALLEL=6 MODEL_ID=codex:gpt-5.3-codex make sweep
```

Result: `97.7%` (`43/44`) at `236s` wall.

Miss:

- `t16`: missing required product ref
  `/proc/catalog/paints_finishes/wall_paint/fam_paints_finishes_wall_paint_0002_33m7fvug/PNT-H3KGOE8C.json`.

Security grep: clean.

Decision: keep as a positive move from the current 41-42/44 regression profile,
but do not call the goal complete. Remaining instability is still the t16
variant/ref-policy cluster.
