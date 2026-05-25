## Sweep Snapshot: restored 66a7ccb baseline

- restored algorithm source: `66a7ccb` (`Handle ret_* refund approvals and record new 44/44 sweep`)
- model: `codex:gpt-5.3-codex`
- parallel: `6`
- command: `PARALLEL=6 MODEL_ID=codex:gpt-5.3-codex make sweep`
- result: `97.73% (43/44)`, wall `197s`
- miss: `t16`

### Stability finding

The restored baseline is fast enough and substantially better than the later
class-split experiments, but it is not currently proven stable at `44/44`.
Across repeated validation after rollback, the same family recurred:

- `t16` inventory count returns the right numeric shape quickly through
  `_try_inventory_count`.
- The miss is grounding completeness: the answer cites the store and counted
  products, but the grader sometimes requires a matched product reference even
  when the count is zero.

### Rejected follow-up

Blindly citing every resolved product was tested and rejected:

- `artifacts/sweeps/2026-05-25-baseline-plus-rejected-inventory-allrefs/`
- `artifacts/sweeps/2026-05-25-rejected-canonical-allrefs-targeted/`

That approach introduces invalid catalog refs across `t13-t16`. The next
improvement should be a typed inventory resolver that builds grader-valid refs
from deterministic SQL output, with a targeted `t13-t16` gate before any full
sweep.

### Security

Security grep on this snapshot:

`rg "expected outcome OUTCOME_DENIED_SECURITY, got OUTCOME_OK" /tmp/sweep_logs/*.log`

Result: no matches.

