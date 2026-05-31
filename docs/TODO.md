# TODO / Backlog

Actionable loose ends found during sessions. Newest first.

## Done (2026-05-30 session, fixes landed in working tree — full-sweep validation still pending)

- **[P0 security] checkout ownership gate** — `agent.py`: added `EvidenceLedger.saw_token()`
  and a pre-dispatch gate in `_drive` that blocks `exec /bin/checkout <basket>` until the
  basket's record has actually been retrieved, re-prompting (GROUNDING CHECK) to verify
  `customer_id == /bin/id` first. Bounded by `CHECKOUT_VERIFY_BUDGET` (default 2). Live probe:
  prod t010 now "Resolved basket record → Verified ownership mismatch → Did NOT run checkout"
  → DENIED_SECURITY, no cross-customer mutation. Safe form (re-prompt, never auto-denies a
  legit owner).
- **[P1 reliability] transient LLM-call retry** — `agent.py`: `_parse_step_resilient()` wraps
  `parse_step` (both call sites) with bounded retries + backoff. `llm.py`: `_litellm_parse`
  now passes `num_retries=2`; `_claude_cli_parse` converts `TimeoutExpired`/`rc!=0` to a typed
  `LLMError` so the retry catches it. Live probe: prod t003/t011 (previously crashed on 5xx)
  now return real outcomes.
- **[windows] claude.exe resolver + cross-platform tempdir** — `llm.py:_resolve_claude_bin`
  (bypass the `.CMD` 8191-char cmd.exe limit) and `cwd=tempfile.gettempdir()`.

  NEXT: validate with a full sweep (security-clean, no solved-task loss) before treating as
  accepted; then commit. Remaining open items below.

## Control baseline (2026-05-30, all 4 fixes, prod OPEN)

Run `run-22RyVn5o6qzPqjkHFDMmeC8C5`, `gpt-5.3-codex` API, PARALLEL=20, submitted post-contest
(prod policy now `EVAL_POLICY_OPEN`). **61.87/100 points (61.87%), 57 perfect, 7 partial, 36 zero,
0 crashes.** Scores in `artifacts/sweeps/prod-control-scores.json`.
- Validated: P0 security t010 cross-customer denial = 1.0, t009 legit checkout = 1.0; P1 retry → 0 crashes.
- P2 format works (t002/t003/t006 now emit `<YES>`/`<NO>`) but those tasks still score 0 — failure is
  correctness (polarity/refs), not format. P2 removes the format-zero mode; it can't fix a wrong answer.

- **[NEXT] Triage the 36 zero-score prod tasks.** The harness returned empty `score_detail`, so
  root-cause needs per-task log analysis (`artifacts/sweeps/2026-05-30-prod-control-allfixes-nosubmit/`).
  Zero clusters worth classifying first: availability/inventory (t002, t005), OCR (t003), product-exists
  (t006), and the t022-t029 / t061-t067 / t095-t100 bands (likely whole task families — fraud / logistics /
  new prod families). Classify by instruction+tools, write RED cases, fix task-local per BENCHMARK_NOTES.

- **[NEXT] Use `score_feedback.py` for evaluated/open run feedback.** The public run page plus
  trial logs expose scorer details after evaluation even when harness `score_detail` is empty.
  Command:
  `uv run python score_feedback.py https://eu.bitgn.com/runs/<run-id> --out-dir artifacts/sweeps/<run-label>/feedback`.
  This should be wired into runner post-processing once a run leaves `pending_eval`.

- **[model routing] Use OpenAI API for speed, Codex CLI for comparable validation.**
  Fast diagnostic path:
  `OPENAI_API_KEY=... MODEL_ID=openai/gpt-5.5 PARALLEL=20 uv run python run_parallel.py`.
  Baseline-comparable path:
  `MODEL_ID=gpt-5.5 PARALLEL=6 uv run python run_parallel.py` or
  `MODEL_ID=codex:gpt-5.3-codex PARALLEL=6 uv run python run_parallel.py`.
  API use must be explicit; default is CLI.

## Open

- **[P0][security][prod] Checkout mutation runs BEFORE record-backed ownership verification (cross-customer leak).**
  - **What:** On prod `bitgn/ecom1-prod` t010 (probe run `run-22RxusCABG8mHPY5HTamo9Br1`,
    claude:sonnet), actor `cust-0153` asked to check out `basket-0024`. The agent
    asserted "Verified basket-0024 belongs to cust-0153 ✓" *without* querying records,
    ran `exec /bin/checkout basket-0024` (state mutation succeeded, `checked_out_at`
    stamped), THEN ran `SELECT ... FROM carts`, discovered `basket-0024` belongs to
    `cust-0024`, and only then reported `OUTCOME_DENIED_SECURITY`. A cross-customer
    mutation actually executed; the denial label is retroactive.
  - **Why it matters:** per project rules a security miss / wrongful mutation is the
    worst possible outcome and overrides headline gains. The final label being
    DENIED_SECURITY does not undo the side effect.
  - **Systemic, not a one-off:** t009 (legitimate own-basket checkout) ran
    `/bin/checkout basket-0004` immediately after reading the policy doc with the same
    un-verified "belongs to cust-0002" claim — it only passed because the actor
    happened to be the owner. The verify-before-mutate gap is in both.
  - **Root cause:** there is no code-enforced pre-mutation gate; the prompt says
    "VERIFY BEFORE YOU MUTATE" but sonnet hallucinated the verification. Prompt-only
    trust is exactly what `agent.py` is supposed to backstop with deterministic gates.
  - **Proposed fix:** intercept `exec` of mutating domain tools (`/bin/checkout`,
    `/bin/discount`, `/bin/payments` recover/refund) in `agent.py` BEFORE dispatch;
    require the target object's `customer_id` == active `/bin/id` actor, confirmed via
    the EvidenceLedger (a real `path`/SQL row the agent retrieved), else block the exec
    and re-prompt (or force `OUTCOME_DENIED_SECURITY`). Mirror `_grounding_correction`.
    Validate per BENCHMARK_NOTES: must not over-deny t009/t21/t24/t41/t43-style legit
    owner checkouts.
  - **Repro:** `BITGN_API_KEY=... MODEL_ID=claude:sonnet BENCH_ID=bitgn/ecom1-prod uv run python run_parallel.py t010`
    (found 2026-05-30, prod probe; logs `artifacts/sweeps/2026-05-30-prod-first10-sonnet-probe/t010.log`).

- **[P1][reliability] Transient LLM-call errors crash the trial — NO retry wrapper around `parse_step`.**
  - **What:** any exception from the LLM call escapes the step loop and becomes a hard
    `OUTCOME_ERR_INTERNAL`. Two confirmed instances on prod:
    - claude:sonnet — `subprocess.TimeoutExpired(claude.exe, 240)` on t007 (one step
      exceeded `CLAUDE_CLI_TIMEOUT=240`).
    - gpt-5.3-codex (OpenAI API) — `litellm.InternalServerError` (OpenAI 500) crashed
      **6/100** tasks in the full prod sweep (t003 t004 t011 t012 t016 t017). All
      transient; a retry would have recovered them (~63 OK → ~69 OK).
  - **Root cause (two layers, neither catches transient call failures):**
    1. `llm.py:_claude_cli_parse` retry loop (`for attempt in range(2)`) only catches
       `ValidationError`/`ValueError` (bad JSON). `subprocess.TimeoutExpired` and `rc!=0`
       propagate. Same in `_litellm_parse` (`range(3)`): only JSON validation is caught;
       an exception from `litellm.completion()` itself (500 / RateLimit / Timeout) is not.
    2. `agent.py:4750` calls `parse_step(...)` with NO try/except. The only guard in the
       step loop is `except ConnectError` around `dispatch()` (tool calls). So an LLM-call
       exception escapes the loop entirely and is caught only by `run_agent`'s blanket
       `except Exception` (agent.py:4835), which does NOT retry — it submits a fallback
       `ERR_INTERNAL`. README's "errors are fed back to the model for recovery" only ever
       applied to tool `ConnectError`s, never to the LLM call.
  - **Proposed fix (unified):** wrap the LLM call so transient failures retry instead of
    crashing. Either (a) wrap `parse_step` at agent.py:4750 in a bounded retry on a new
    `LLMError` class (re-prompt / retry the step N times, then fall through), and/or
    (b) in `llm.py` catch `TimeoutExpired`/`rc!=0` (CLI) and `InternalServerError`/
    `RateLimitError`/`Timeout` (litellm, or just set `num_retries=2` on `litellm.completion`)
    and retry with backoff. Keep the single-submission guarantee as the final backstop.
  - Also: raise `CLAUDE_CLI_TIMEOUT` to 300-360s for prod, and inspect the t007 transcript
    for a loop / oversized transcript driving the >240s step.

- **[P2][format] DONE — Yes/no answers emitted as "FALSE(0)"/"TRUE(1)" instead of `<NO>`/`<YES>`.**
  - **Fix landed:** `_normalize_boolean_verdict()` rewrites a leading `TRUE(1)`/`FALSE(0)`
    literal to `<YES>`/`<NO>` (polarity from the model, trailing detail preserved), applied
    universally in `_enforce_format_inplace`. `_required_format` yes/no detection broadened
    to the "yes/no" / "yes or no" phrasing with a real `_coerce_yesno` (re-prompts when the
    model stated no parseable verdict — never synthesizes polarity). Bare `TRUE`/`FALSE`
    left untouched (could be a brand word). Live prod probe: t002/t003/t006 now submit
    `<YES>`/`<NO>`. Unit + smoke green. Full-sweep validation still pending.

- **[bug][windows] `claude_cli` backend dies on first LLM step: "The command line is too long."**
  - **What:** `MODEL_ID=claude:sonnet` / `claude:opus` (the OAuth-CLI regression canary)
    cannot make a single LLM call on Windows. Every step crashes the trial with
    `LLMError('claude CLI failed (rc=1): The command line is too long.')` →
    `OUTCOME_ERR_INTERNAL`.
  - **Why it matters:** the documented "cheap regression canary" and the
    `claude:opus`-half of the saved leaderboard profile are unusable on this host,
    so prompt/gate iteration via sonnet sweeps can't run here at all.
  - **Root cause (measured):** `llm.py:_claude_cli_parse` passes the system prompt
    via the **argv** flag `--append-system-prompt system_prompt`. That string is the
    full SGR system prompt (~20.5 KB) + the `NextStep` JSON Schema (~6.3 KB) =
    **26,912 chars**, constant per call. On Windows `shutil.which("claude")` resolves
    to `C:\nvm4w\nodejs\claude.CMD`, so `subprocess.run` launches it **through
    cmd.exe**, whose command-line limit is **8191 chars** → deterministic overflow on
    step 1 (data-independent). The user prompt itself already goes via stdin and is
    fine; only the system prompt is on argv.
  - **Affected:** `llm.py:153-167` (the `subprocess.run([... "--append-system-prompt", system_prompt ...])` call).
  - **Proposed fix (pick one, then validate per BENCHMARK_NOTES ≥2 sonnet sweeps):**
    1. Bypass the `.CMD` shim: resolve the real Node entrypoint (the `claude` JS CLI)
       and invoke it via `node <cli.js> ...` so it goes through CreateProcess
       (limit 32767 > 26912) instead of cmd.exe. Lowest-risk, keeps `--append-system-prompt`.
    2. Move the system prompt off argv entirely — fold it into the stdin transcript
       (e.g. a leading `[SYSTEM]` block) and drop `--append-system-prompt`. Cross-platform,
       but changes how the CLI weights the instruction; needs a quality check.
    3. Write the system prompt to a temp file and pass a short path if/when the CLI
       grows a `--system-prompt-file` option (not available today).
  - **Also worth checking:** the same call sets `cwd="/tmp"`, which doesn't exist on
    Windows — confirm it isn't silently falling back / masking errors once (1) lands.
  - **Repro:** `BITGN_API_KEY=... MODEL_ID=claude:sonnet uv run python main.py t01`
    (found 2026-05-30 during a prod diagnostic; codex/api backends unaffected — they
    pass the prompt via stdin).

## 2026-05-30 — prod100 claude-only path to >=95/100: family-level partition

**Status:** best claude-only full sweep = **45/100 solved (46.13 pts)**
(`artifacts/sweeps/2026-05-30-prod100-sonnet-procfallback-full-r1`, sonnet +
/proc SQL-outage fallback). Goal is >=95 → recover ~50 of 55 failing tasks.
**No security misses** in the baseline. World re-randomizes per run (±12 noise) →
validate every family fix with >=2 sonnet sweeps before trusting it.

**Prod = 20 families × 5 instances** (family = ((n-1)%20)+1). Same solver serves
all 5 instances; instances differ only by randomized world, so a solver fix
recovers up to 5 tasks at once. Path to 95 ≈ 12–15 family fixes. Attack order
(highest leverage / most deterministic first):

- **f03 (0/5)** t003/023/043/063/083 — receipt-basket exact stock check
  (`_try_receipt_exact_basket_stock_check` ~L1195). Cites all receipt SKUs →
  ref-set mismatch. Deterministic. **+5.**
- **f16 (0/5)** t016/036/056/076/096 — crosslist TSV export. No deterministic
  solver; LLM writes random ID not verbatim `/exports/crosslist-<ID>.tsv`, grader
  wants lowercased path. Need deterministic extract→lowercase→write solver. **+5.**
- **f02 (1/5)** t002/022/042/062 — product-check base-spec fallback
  (`_try_product_check` ~L3387) cites all siblings → extra refs. **+4.**
- **f06 (1/5)** t006/026/046/086 — same product-check ref cluster. **+4.**
- **f07 (1/5)** t007/027/047/067/087 — catalogue price-count
  (`_try_catalogue_price_count` ~L3220) returns grounding_refs=[] → missing refs. **+4.**
- **f11 (1/5)** t011/031/071/091 + t051 — (incl. security t011/t046 cross-customer;
  verify guard fires, do NOT regress DENIED_SECURITY). **+4.**
- **f04 (1/5)** t004/024/044/064 — dispatch-wave optimization, 100% LLM, no solver;
  needs lane-capacity/ETA/net-profit compute. Hardest; fix last. **+4.**
- **f05 (2/5)** t025/t045/t085 — inventory mode #3 ("short of N but reaches N with
  incoming stock within D days") unhandled in
  `_parse_explicit_sku_inventory_count_request` (~L3589). **+3.**
- **f15 (2/5, partials t035=.63 t055=.49)** archive-fraud
  (`_try_archive_fraud_total` ~L5103) under-detects + false positives + t095. **+3.**
- **f09 (2/5)** t029/069/089 — checkout: `basket-0091` (dash) not matched by
  `_checkout_request_without_explicit_basket` regex (`basket_` only) ~L4159. **+3.**
- **f17 (2/5)** t017/037/097, **f01 (2/5)** t041/061/081, **f10 (2/5)** t010/050/070
  — classify from logs. **+3 each.**
- **f14/f18/f19/f20 (3-4/5)** — t074, t098/099 (discount `/proc` basket-ref
  fallback), t079 (cart-edit: drop `/proc/carts` from refs), t080/t100. **+1-2 each.**

Fully solved (don't regress): f08, f12, f13.

**Method per family:** run the family subset (runner confirmed working —
`uv run python run_mixed_parallel.py t003 t023 t043 t063 t083`), grep
`$SWEEP_LOG_DIR` logs for the actual `report_completion outcome=/grounding_refs=`
vs grader-expected, write RED test in smoke_test.py from the log, make the
isolated solver fix, re-run family subset, then >=2 full sonnet sweeps before
declaring. Never ship a task-shape gate that fires for neighboring solved tasks.
