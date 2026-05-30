# TODO

## P0 - Score and Submission Correctness

- Record final public scores for prod R9 (`run-22RyBLkxE4jAAJKgXGUsJ6WW7`) and
  R6 (`run-22Rxi4mh3BZQYwepCzSHUnGxD`) once BitGN leaves `pending_eval`.
- Fix category submission metadata before any future leaderboard attempt:
  persist intended category, model family, route manifest, and reject mismatches
  such as Codex/Spark submitted as Open Weights.
- Add a post-close poller/scraper for `/me/runs` or public run pages so the
  repo records exact points, max points, public time, category, and evaluation
  state automatically.
- Make leaderboard submit criteria points-first: submit only if exact points are
  better, or exact points tie and public/platform time is faster, unless the run
  is explicitly diagnostic.

## P0 - Runner Reliability

- Retry LLM timeouts before `SubmitTrial`. The current fallback submits
  `OUTCOME_ERR_INTERNAL`, which permanently burns that trial inside the same
  run.
- If continuation is possible, support leaving a timed-out trial/run open rather
  than closing it with an internal answer.
- Add rate-limit handling around platform and model calls: parse `Retry-After`,
  quota text, and usage-limit errors; throttle instead of launching a doomed
  sweep.
- Do not open a BitGN trial until a model worker slot is actually ready. Track
  `trial_open_seconds`, `agent_seconds`, and `model_wait_seconds` separately.

## P0 - Prod Fast-Path Tests

- Add smoke coverage for scoped `/tmp/*.tmp` cleanup. R9 carried a regex bug in
  the live run; the regex was corrected afterward, but the branch still needs a
  regression test.
- Add smoke coverage for latest-active-basket edits through `/proc/carts`.
- Add smoke coverage for JSON catalogue yes/no and SKU lookups through
  `/proc/catalog`, including negative cases that must not overmatch.
- Add a test fixture for simulated SQL/ODBC outage: first SQL failure should
  fall back to `/proc`/`/docs`, not `OUTCOME_ERR_INTERNAL`.

## P1 - Model Routing

- Keep Spark as a speed route only when quota is known available. Add a canary
  that stops Spark routing immediately after the first quota error.
- Keep ordinary `codex:gpt-5.3-codex` as the safer fallback for post-quota full
  runs, but tune per-step timeout/retry so a single 600s call does not sink a
  task.
- Do not use Opus for bulk 100-task tournament runs without a narrow hard-task
  route; it was too slow in the prod profile tested.
- Maintain a category-aware route manifest so the submission category can be
  audited after the run.

## P1 - Competition Operations

- Preserve a compact per-run `candidate_decision.md` in every sweep directory:
  run id, benchmark id, model route, whether it was closed, whether it was
  submitted to a category, exact local hard-fail list, and public score state.
- After every full run, classify non-perfect or hard-fail tasks immediately:
  security miss, full miss, expensive partial, new condition, flaky old task.
- For any task selected for fixing, run isolated samples first, write RED tests
  from concrete logs, and make one task-local fix before the next full run.
- Keep dev and prod baselines separate. Prod pending-eval runs are evidence, not
  accepted baselines, until exact points are visible.
