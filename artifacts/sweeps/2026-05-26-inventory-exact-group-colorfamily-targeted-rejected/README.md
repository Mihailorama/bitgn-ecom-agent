# 2026-05-26 Color Family And Battery Alias Targeted Rejected

Command:

```bash
PARALLEL=6 MODEL_ID=codex:gpt-5.3-codex TASKS='t13 t14 t15 t16 t32' make sweep
```

Result: `80.0%` (`4/5`) at `36s` wall.

Rejected follow-up guesses:

- `color family` matching `colour_family`
- `battery platform` matching alternate battery-system keys

Miss: `t16` still missed a required product ref. These aliases were reverted
from runtime code after smoke, and the next step is resolver diagnostics rather
than more alias stacking.
