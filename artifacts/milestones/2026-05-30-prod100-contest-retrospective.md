# 2026-05-30 prod100 contest retrospective

## Summary

Benchmark: `bitgn/ecom1-prod`, blind, 100 trials, 3-hour contest window.

Final public score was not visible when this retrospective was written. Both
submitted runs still showed `pending_eval` and score `-`, so the repo keeps the
dev53 `53.00/53` run as the last score-known accepted baseline.

Submitted runs:

- Accuracy: R9, `run-22RyBLkxE4jAAJKgXGUsJ6WW7`.
- Open Weights nomination: R6, `run-22Rxi4mh3BZQYwepCzSHUnGxD`. This was run
  with Codex Spark, so treat the category as likely invalid.

## Run Timeline

| label | run id | logs | route | outcome |
|---|---|---|---|---|
| R1 | `run-22RxEwAqh9bhf2k33uoWF2noK` | `artifacts/sweeps/2026-05-30-prod100-mixed-opus-spark-r1/` | mixed Opus/Spark | Too slow; 95 nonzero local summaries, many simulated SQL/ODBC internals; not candidate. |
| R2 | `run-22RxWmkHCPNF5XQfSQ7EMcA3t` | `artifacts/sweeps/2026-05-30-prod100-all-spark-r2-sqlfix/` | all Spark | Early SQL-fix canary, stopped early. |
| R3 | `run-22RxZbAoqPU4hnWJ7GGqFDxiW` | `artifacts/sweeps/2026-05-30-prod100-all-spark-r3-no-sql-retry/` | all Spark | No-SQL-retry canary, closed mainly to test SubmitRun behavior. |
| R6 | `run-22Rxi4mh3BZQYwepCzSHUnGxD` | `artifacts/sweeps/2026-05-30-prod100-all-spark-r6-nosubmit/` | all Spark | Completed 100/100 local summaries; 2 local internals (`t056`, `t059`); no security miss; public page pending. |
| R7 | `run-22RxsQJrDqLJikgwKPZhB5dn5` | `artifacts/sweeps/2026-05-30-prod100-all-spark-r7-employee-crosslist-fix/` | all Spark | Rejected: Spark quota exhausted mid-run. |
| R8 | `run-22RxuMeNSPib3hcipyf9QkHKG` | `artifacts/sweeps/2026-05-30-prod100-all-codex53-r8-post-spark-limit/` | all Codex 5.3 | Completed 100/100 local summaries; 4 local internals (`t001`, `t026`, `t039`, `t079`); no security miss; not submitted. |
| R9 | `run-22RyBLkxE4jAAJKgXGUsJ6WW7` | `artifacts/sweeps/2026-05-30-prod100-all-codex53-r9-emergency-fastpaths/` | all Codex 5.3 plus emergency fast paths | Completed 100/100 local summaries; 2 local internals (`t039`, `t047`); no security miss; submitted to Accuracy; public page pending. |

## Final Submitted Evidence

R9 public page evidence at documentation time:

- State: `pending_eval`.
- Started: May 30, 2026 at 10:37 UTC.
- Submitted/evaluated timestamp: May 30, 2026 at 11:05 UTC.
- Trials done: 100.
- Trials with error: 0.
- Total trial time: `147 min 23 sec`.
- Score: `-`.

R6 public page evidence at documentation time:

- State: `pending_eval`.
- Started: May 30, 2026 at 09:27 UTC.
- Submitted/evaluated timestamp: May 30, 2026 at 09:45 UTC.
- Trials done: 100.
- Trials with error: 0.
- Total trial time: `99 min 16 sec`.
- Score: `-`.

## What Changed In Prod

- Denominator grew from dev53 to 100 tasks.
- Some old task families changed wording, so the first 53 were not guaranteed to
  be identical to dev.
- OCR, `/proc` JSON discovery, `/docs` rules, and `/AGENTS.MD` became central.
- Simulated `ODBC Driver 18` and SQL outage strings were deliberate task
  conditions, not platform failures.
- Scores were issued only after `SubmitRun`; the live UI could show a run as
  running or awaiting scores for a long time.
- Rate limits and model quotas mattered more than in rehearsals.

## What Worked

- The no-security-miss posture held across the complete local R6/R8/R9 profiles.
- Switching away from SQL after simulated outage reduced false internals.
- Ordinary Codex after Spark quota avoided the quota failure class.
- Emergency deterministic fast paths reduced the hard-fail set from R8's four
  local internals to R9's two local internals.
- Manual `SubmitRun` recovery worked after earlier runner submit/close bugs.

## What Failed

- Spark quota was exhausted during R7, so a quota-aware router is mandatory.
- Opus was too slow for the bulk 100-task profile.
- R6 was submitted as Open Weights even though it used Codex Spark. Future
  category submission needs a model-family guard.
- The runner burns timed-out trials by submitting `OUTCOME_ERR_INTERNAL`; that
  prevents same-run retry.
- R9's scoped `.tmp` cleanup fast path had a regex bug in the live run. The
  regex was corrected afterward, but the branch needs smoke coverage.
- Local `sweep_report.json` is not a reliable score source for blind prod runs
  when `NO_SUBMIT=1` or delayed `SubmitRun` is involved.

## Immediate Follow-Ups

1. Poll the public/authenticated run pages until R6/R9 leave `pending_eval`; then
   update `RESULTS.md` with exact points and category result.
2. Add timeout retry before `SubmitTrial`.
3. Add category guard and route metadata before the next submission.
4. Add smoke tests for the three emergency fast paths added during prod:
   scoped tmp cleanup, latest basket add, and JSON catalogue lookup.
5. Add SQL-outage fallback tests so simulated ODBC conditions become
   deterministic `/proc`/`/docs` work instead of internals.
6. Keep prod pending-eval runs separate from accepted score-known baselines.
