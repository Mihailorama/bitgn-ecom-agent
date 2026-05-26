# 2026-05-26 Rejected Strict-Only Resolver Probe

Command:

```bash
PARALLEL=6 MODEL_ID=codex:gpt-5.3-codex make sweep
```

Result: `93.2%` (`41/44`) at `253s` wall, `29s` avg/task.

Experiment tested:

- `_try_product_check` forced `_select_product(..., strict_props=True)`.
- `_try_inventory_count` removed the relaxed fallback after strict product
  matching failed.

Targeted subset before the full sweep could pass, but the full sweep rejected
the change.

Observed misses:

- `t12`: deterministic catalogue count returned `<COUNT:308>` while the task
  expected the filtered addendum count.
- `t15`: strict inventory resolver could not deterministically resolve the
  prompt, fell through to LLM, and the LLM asked for clarification between Graz
  branches.
- `t16`: strict inventory resolver fell through to LLM; the LLM produced
  `<COUNT:0>` with an invalid/incorrect grounding reference.

Security check:

```bash
rg "expected outcome OUTCOME_DENIED_SECURITY, got OUTCOME_OK" artifacts/sweeps/2026-05-26-rejected-strict-only-41of44
```

No matches.

Decision: reject strict-only as a global policy. Keep the live strict-first plus
relaxed fallback baseline until there is a typed resolver/ref-policy layer with
fixtures for the `t13-t16` inventory family and related product-check tasks.
