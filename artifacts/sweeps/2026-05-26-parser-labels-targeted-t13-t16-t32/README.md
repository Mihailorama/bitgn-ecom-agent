# 2026-05-26 Parser Labels Targeted Sweep

Command:

```bash
PARALLEL=6 MODEL_ID=codex:gpt-5.3-codex TASKS='t13 t14 t15 t16 t32' make sweep
```

Result: `100.0%` (`5/5`) at `40s` wall.

Experiment: add parser support for high-density product labels from the rejected
exact-variant branch (`tank volume`, `grip type`, `fit`) without changing
inventory ref policy.

Decision: targeted signal was good, but the next full sweep still missed
inventory refs, so parser labels alone are insufficient.
