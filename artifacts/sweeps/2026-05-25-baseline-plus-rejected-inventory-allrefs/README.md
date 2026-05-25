## Sweep Snapshot: 2026-05-25 rejected inventory all-refs patch

- base: `agent.py` restored to `66a7ccb` plus one experimental change
- experimental change: deterministic inventory cited all resolved product refs
  instead of only counted/available product refs
- model: `codex:gpt-5.3-codex`
- parallel: `6`
- result: `88.64% (39/44)`, wall `285s`

### Verdict

Rejected. The change fixed the observed missing-ref shape in one baseline run
but caused broad `t13-t16` invalid-reference regressions. Keep the rollback to
the `66a7ccb` algorithm and use this snapshot only as evidence that inventory
grounding must be solved with a stricter per-format/per-ref resolver, not by
blindly citing every resolved product.

