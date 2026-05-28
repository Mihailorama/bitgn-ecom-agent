# 2026-05-28 dev53 harness rehearsal plan

## Current State

Observed on 2026-05-28:

- `bitgn/ecom1-dev` now exposes `53` tasks: `t01` through `t53`.
- The three new tasks are expected to be OCR tasks, but their concrete shapes
  must come from fresh logs, not assumptions.
- Current local accepted milestone remains the last fully accepted `50.00/50`
  result on the previous denominator:
  `artifacts/sweeps/2026-05-28-t48-rowlevel-fix6-full-codex55-r1/`.
- That `50/50` result is not directly comparable to the new `53`-task
  denominator; it is the old-task baseline for `t01` through `t50`.
- The worktree already has tracked changes for the accepted t48 fix, docs, and
  the harness-compatibility patch below. Existing untracked sweep logs and
  `.antigravitycli/` remain diagnostic leftovers and should not be committed
  automatically.

## Harness Changes To Handle First

The official Python sample now treats `SubmitRun` as the scoring boundary:

- workers still call `EndTrial`;
- task scores are read from `SubmitRunResponse.trials`;
- final run score is read from `SubmitRunResponse.score`;
- if the run is not submitted/closed, score may be unavailable.

Local issue before the compatibility patch:

- `run_parallel.py`, `run_mixed_parallel.py`, and `main.py` still build reports
  from `EndTrialResponse.score`.
- The currently pinned BitGN protobuf SDK only exposes `SubmitRunResponse` as
  `run_id,state`; it cannot read the new batch score fields.
- Buf has a newer `20260528115439+d3855da61ce2` SDK build where
  `SubmitRunResponse` includes `score`, `score_available`, and `trials`.

The compatibility patch added in this session updates the SDK pins and teaches
the runners to merge post-submit scores back into local result rows. A dev53
rehearsal can now measure batch scores, but leaderboard intent still needs to
be handled carefully because closing the run is required for scoring.

One live check showed that `StartRun` now rejects an empty `BITGN_API_KEY`, so
anonymous diagnostic runs are not available on the public dev contour. Until a
separate non-leaderboard scoring mode is confirmed, every live run must be
treated as potentially leaderboard-visible.

## Implementation Plan

1. Add a small harness-compatibility patch. Done.
   - Bump BitGN Buf SDK pins to the 2026-05-28 build.
   - Add a helper that merges `SubmitRunResponse.trials` scores into the local
     result rows.
   - Keep a fallback for old `EndTrialResponse.score` so older harness behavior
     still works.
   - Update `run_parallel.py`, `run_mixed_parallel.py`, and `main.py`.
   - Keep filtered-out subset trials incomplete until `SubmitRun(force=True)`,
     matching the official sample, so skipped tasks are not scored as blank
     answers.
   - Add smoke tests for "EndTrial unscored, SubmitRun scored".

2. Separate diagnostic close from leaderboard intent.
   - Under the new harness, a run must be closed to get a score.
   - If `SubmitRun` is also the leaderboard publish point, post-run local
     submit gating is no longer sufficient.
   - Empty API-key diagnostic runs were rejected by `StartRun`.
   - Live diagnostic rehearsals therefore need explicit approval if they may
     appear as submitted runs.
   - Record in every `sweep_report.json` whether the run was diagnostic or
     leaderboard-intended.

3. Add rate-limit handling before broad rehearsals. Parser/backoff helper done.
   - Treat `CodeResourceExhausted` / `RESOURCE_EXHAUSTED` as wait-and-retry.
   - Parse wait seconds from the error message when available.
   - Respect the announced limit: `10` runs per `30` minutes.
   - For repeated isolated evidence, batch related task IDs into one run when
     possible, for example `t51 t52 t53` together for OCR sampling.

4. Run a dev53 diagnostic full sweep.
   - Use a unique `SWEEP_LOG_DIR`.
   - Keep current strong profile first:
     `run_mixed_parallel.py`, all tasks routed to `codex:gpt-5.5`, parallel `6`.
   - Expected first output is not an accepted baseline; it is a map of changed
     old tasks plus new OCR tasks.

5. Triage automatically after the full sweep.
   - Security miss: immediate reject and stop.
   - Old-task regression in `t01` through `t50`: highest priority.
   - New OCR tasks `t51` through `t53`: next priority.
   - Partial tasks after full misses, ordered by lost points.

6. OCR evidence cycle.
   - Run `10` diagnostic subset sweeps containing all OCR task IDs together.
   - Save logs in unique directories.
   - Classify whether the task needs image/OCR extraction, docs/rules lookup,
     SQL correlation, or strict response formatting.
   - Only then add RED tests and one narrow OCR/local-file capability.

7. Acceptance gate for dev53.
   - Primary objective is points, not perfect-count.
   - Keep `score_pct >= 98%`.
   - Preserve old-task baseline: no regression on `t01` through `t50`.
   - Accept a dev53 baseline only after a full sweep with no security miss.

## Tournament Rehearsal Loop

The three-hour tournament loop should be:

1. Run one full diagnostic sweep and close it so the batch score is available.
2. Auto-sort non-perfect tasks by lost points and security risk.
3. For the top family, collect `10` isolated/subset samples.
4. Write RED tests from concrete logs.
5. Make one task-local fix.
6. Run targeted subset, then one full sweep.
7. Accept only if points and percent gates improve or preserve the current
   accepted baseline and security remains clean.

Do not spend the first tournament hour on broad resolver rewrites. The fastest
adaptation path is runner correctness first, then evidence-driven task-local
fixes.
