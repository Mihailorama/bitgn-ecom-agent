## Sweep Snapshot: 2026-05-25 baseline 66a7ccb validation

- algorithm: `agent.py` restored to commit `66a7ccb`
- model: `codex:gpt-5.3-codex`
- parallel: `6`
- command: `PARALLEL=6 MODEL_ID=codex:gpt-5.3-codex make sweep`
- result: `97.73% (43/44)`, wall `218s`

### Miss

- `t16`: deterministic inventory count returned the right outcome shape but
  missed a required product grounding reference.

### Security

- `rg "expected outcome OUTCOME_DENIED_SECURITY, got OUTCOME_OK" /tmp/sweep_logs/*.log`
- result: no matches.

### Interpretation

The historical `44/44` baseline is still fast and close, but it is not proven
stable: two restored-baseline validation sweeps in this cycle produced `43/44`,
both with a single `t16` inventory grounding miss. Improve from this point only
with a narrow inventory ref resolver; broad class-split and "cite all products"
experiments regressed other inventory tasks.

