# 2026-05-26 Current Baseline Regression Sweep

Command:

```bash
PARALLEL=6 MODEL_ID=codex:gpt-5.3-codex make sweep
```

Result: `93.2%` (`41/44`) at `236s` wall, `29s` avg/task.

Purpose: re-check the restored fast baseline after the 2026-05-25 rollback and
preserve full per-task logs for the current instability cluster.

Observed misses:

- `t15`: deterministic `_try_inventory_count` returned `<COUNT:2>`; expected
  task outcome was a lower exact count.
- `t16`: deterministic `_try_inventory_count` returned `[QTY:2]` but missed a
  required product reference in the dense inventory variant family.
- `t32`: LLM product/property check selected a plausible but wrong catalogue
  SKU/ref (`AUT-2W4O7G21`).

Security check:

```bash
rg "expected outcome OUTCOME_DENIED_SECURITY, got OUTCOME_OK" artifacts/sweeps/2026-05-26-current-regression-41of44
```

No matches.

Conclusion: current runtime is still capable of fast perfect runs historically,
but it is not stable. The repeated failure shape is product variant resolution
and grounding refs, mostly around deterministic inventory and related catalogue
property checks.
