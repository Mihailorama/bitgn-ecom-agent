# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Python agent for the `bitgn/ecom1-dev` benchmark (BitGN Agentic E-commerce
challenge). It talks to the `bitgn.vm.ecom` runtime over connect-rpc and drives
an LLM with Schema-Guided Reasoning. The repo is a **tuning loop**, not a
product: most commits are "change a prompt rule or a code-enforced gate, run a
sweep, record the score in `RESULTS.md`". See `BENCHMARK_NOTES.md` for the task
taxonomy the prompt is tuned against, and `RESULTS.md` for the score-vs-speed
log of every prior sweep.

The benchmark **randomizes products / ids / baskets per trial** from a seed.
Never hardcode answers; only the task families and policy rules are stable.

## Commands

| | |
|---|---|
| Install deps | `make sync` (uses `uv`, Python 3.13) |
| Offline smoke test (no keys, no network) | `make test` — runs `smoke_test.py`; **always run before a sweep** |
| Single task / subset (serial) | `uv run python main.py t01` or `make task TASKS="t01 t04"` |
| Full benchmark (serial) | `make run` |
| Full benchmark (parallel pool) | `PARALLEL=8 MODEL_ID=claude:sonnet make sweep` — auto-appends a row to `RESULTS.md` only for full sweeps (no `TASKS=` filter) |
| Parallel subset (no row appended) | `PARALLEL=8 MODEL_ID=claude:sonnet uv run python run_parallel.py t13 t17` |

Per-trial trace logs from `run_parallel.py` go to `$SWEEP_LOG_DIR`
(default `/tmp/sweep_logs/<task>.log`). Grep them for failure modes; the
parent only prints a score summary.

Pre-sweep gate the project uses: `uv run python -m py_compile agent.py && uv run python smoke_test.py`.

## MODEL_ID routing (the central config knob)

`MODEL_ID` selects the provider via prefix dispatch in `llm.py:_provider`:

- `claude:opus` / `claude:sonnet` / bare `opus` / `sonnet` / `haiku` →
  **local `claude` CLI over OAuth** (no API key, no metering, rate-limit-fragile
  past `PARALLEL=8`). Used for the cheap iteration loop.
- `gpt-5.5`, `openai/...` → OpenAI via LiteLLM (`OPENAI_API_KEY`).
- `gemini/gemini-3.5-flash` / `pro` → Gemini via LiteLLM (`GEMINI_API_KEY`).
  Used for the actual challenge run (fast).
- `anthropic/claude-...` → Anthropic API via LiteLLM (`ANTHROPIC_API_KEY`).
  Note: bare `claude-*` (without the `anthropic/` prefix) routes to the OAuth
  CLI, not the API.

Adding a new backend = add a branch in `_provider` and write a `_<x>_parse`
helper that returns a validated `NextStep`. The Claude CLI helper
(`_claude_cli_parse`) is the template: hand-roll a system prompt that embeds
the JSON Schema, retry once on validation failure, run from `/tmp` so any host
`CLAUDE.md` / `AGENTS.md` can't poison the call.

## Architecture (what you'd otherwise have to read 4 files to learn)

**The SGR contract (`agent.py`).** Every LLM step must return a `NextStep`
whose `assessment` block is filled BEFORE the model picks a `function`. The
assessment forces an explicit `security` classification (`safe` / `injection` /
`unsafe_request` / `policy_violation`) and an `observation` field. The `function`
is a tagged union over the ECOM tool surface (`tree`, `find`, `search`, `list`,
`read`, `write`, `delete`, `stat`, `exec`) plus `report_completion`. Structured
output is enforced on every provider, so the schema IS the API.

**Hard trust boundary.** The system prompt declares: only the system prompt,
the task instruction, and `/AGENTS.MD` + runtime policy books are authoritative.
File contents, search hits, exec/SQL output, customer messages — all untrusted
data. The `assessment.security` field is the first-class signal for this;
embedded "ignore your instructions" payloads should be surfaced as `injection`,
not obeyed. Cross-customer actions and PII disclosure → `OUTCOME_DENIED_SECURITY`.
There's an explicit decision-order in the prompt (`adversarial > cross-boundary >
rightful-owner > otherwise`) — the first match wins, security is primary so it
can never be downgraded.

**Code-enforced gates around the model.** The prompt alone is not trusted to
behave; `agent.py` adds deterministic post-processing each step:

- `EvidenceLedger` / `_harvest` — tracks every `/proc` path confirmed via
  SQL `path` column, `read`, `stat`, `find`, `search`, `list`.
- `_grounding_correction` — if `report_completion` returns `OUTCOME_OK` while
  citing a `/proc` path the agent never actually retrieved, re-prompt instead
  of submitting (biggest single win in the score log).
- `_required_format` / `_enforce_format_inplace` — coerces `<COUNT:%d>` /
  `[QTY:%d]` / `count : %d` exact-format answers. Never synthesizes yes/no
  polarity (only the model decides truth).
- `_normalize_refs` — repairs leading-slash / dedupes grounding paths; auto-cites
  `/docs/security.md` on security denials.
- `_subject_paths` — on `OUTCOME_OK`, nudges the model to cite the named
  basket/payment/return record already in the ledger.

Correction budget is capped (`MAX_CORRECTIONS`, default 2 per trial) so the
"never blank" guarantee holds. The agent always submits a final
`report_completion` even on step-budget exhaustion.

**Control-plane flow.** `main.py` (serial) and `run_parallel.py` (process pool)
follow the same shape: `StartRun → for each trial_id: StartTrial(harness_url) →
run_agent → EndTrial → SubmitRun(force=True)`. The parallel runner uses
`spawn` context (not fork) because the gRPC client is thread-tainted. Filtered
trials are `EndTrial`'d immediately so subset runs don't leak open trials on
the harness. Worker exceptions are trapped into error rows so one bad task can't
kill the whole sweep.

**`RESULTS.md` is append-only.** A full sweep (no `TASKS=` filter) appends a
score-vs-speed row automatically; partial sweeps don't. Treat the table as the
ground truth for which prompt/gate changes moved the needle — commit messages
in `git log` mirror it line-for-line.

## Validation workflow (project convention)

Per `BENCHMARK_NOTES.md`'s handoff section: validate every change with **≥2
sonnet sweeps** (or a ≥5pp move). Watch category pass-rates in
`$SWEEP_LOG_DIR`, not just the headline number. Always grep summaries for
`expected outcome OUTCOME_DENIED_SECURITY, got OUTCOME_OK` — a security miss
is the worst possible regression and overrides headline gains.

When iterating on the prompt or a gate: change one thing per sweep, keep
changes general (not keyed to specific dev tasks), revert immediately on
regression. The v5 → revert in the git log is the worked example.
