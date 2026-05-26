# 2026-05-26 Exact Group Targeted Rejected

Command:

```bash
PARALLEL=6 MODEL_ID=codex:gpt-5.3-codex TASKS='t13 t14 t15 t16 t32' make sweep
```

Result: `80.0%` (`4/5`) at `93s` wall.

Experiment: resolve exact product candidate groups and choose an available
sibling before citing refs.

Miss: `t16` missing a required LED Bulb ref. Root cause found after inspection:
`colour temperature` was not parsed, so lighting variants were not exact.

Decision: reject this intermediate state; continue with color/colour
temperature parser support.
