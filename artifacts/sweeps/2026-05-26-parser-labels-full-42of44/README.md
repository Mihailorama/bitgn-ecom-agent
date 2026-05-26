# 2026-05-26 Parser Labels Full Sweep

Command:

```bash
PARALLEL=6 MODEL_ID=codex:gpt-5.3-codex make sweep
```

Result: `95.5%` (`42/44`) at `275s` wall.

Misses:

- `t15`: missing required product ref in deterministic inventory.
- `t16`: missing required product ref in deterministic inventory.

Security grep: clean.

Decision: keep the parser-label insight, but parser labels alone do not close
the sibling-ref failure mode.
