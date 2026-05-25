## Sweep Snapshot: 2026-05-25 class-split iteration

- model: `codex:gpt-5.3-codex`
- parallel: `6`
- logs source: `/tmp/sweep_logs/*.log`
- saved at: `artifacts/sweeps/2026-05-25-classsplit-state/`

### Notable runs in this state

- Full sweep: `95.45% (42/44)` with misses on `t09`, `t14`.
- After class-split updates:
  - `t09` isolated rerun: `1.00`
  - `t14` remains unstable (inventory grounding ref selection).

### Security

- `rg "expected outcome OUTCOME_DENIED_SECURITY, got OUTCOME_OK" /tmp/sweep_logs/*.log`
- result: no matches during this snapshot cycle.

