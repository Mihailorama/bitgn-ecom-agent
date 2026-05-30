# BitGN ECOM Agent (SGR)

A competitive Python agent for the [BitGN](https://bitgn.com) `bitgn/ecom1-dev`
benchmark (Agentic E-commerce challenge). Leaderboard:
[bitgn.com/challenge/ecom](https://bitgn.com/challenge/ecom).

It talks to the `bitgn.vm.ecom` runtime (a file-shaped ecommerce OS plus runtime
tools such as `/bin/sql`) over the schema published at
[buf.build/bitgn/api](https://buf.build/bitgn/api), and drives an LLM with
[Schema-Guided Reasoning](https://abdullin.com/schema-guided-reasoning/).

Current accepted leaderboard milestone: `53.00/53` points (`100.00%`) with
`run_mixed_parallel.py` routing default tasks to `claude:opus` and selected
complex tasks to `codex:gpt-5.3-codex-spark`, logs
`artifacts/sweeps/2026-05-29-dev53-mixed-opus-spark-r9-t08-postfix11/`. The
previous codex-only milestone remains `46/47` with `codex:gpt-5.3-codex` at
`PARALLEL=6`, commit `e4a2d41`, tag
`bench-ecom1-dev-v47-46of47-20260526`.

Production contest checkpoint: `bitgn/ecom1-prod` expanded the benchmark to 100
trials and hid scores until run close/evaluation. Two 100/100 submitted runs are
recorded in `artifacts/milestones/2026-05-30-prod100-contest-retrospective.md`:
R9 (`run-22RyBLkxE4jAAJKgXGUsJ6WW7`, Accuracy) and R6
(`run-22Rxi4mh3BZQYwepCzSHUnGxD`, submitted as Open Weights but run with Codex
Spark, so treat the category as likely invalid). Public pages still showed
`pending_eval` and score `-` at documentation time, so the last score-known
accepted milestone remains the dev53 `53.00/53` run above.

## Why this scores well

ECOM grades reliability, **policy compliance**, **security posture**, grounding,
and minimal correct side effects - and it randomly injects ambiguity, missing
context, prompt injection, and unsafe requests. The agent is built around that:

- **SGR assessment on every step.** Before choosing any action the model must
  fill a structured `assessment` block: what it observed, a security
  classification (`safe` / `injection` / `unsafe_request` / `policy_violation`),
  and whether it is genuinely blocked by ambiguity. This forces explicit,
  auditable reasoning about the exact dimensions ECOM measures.
- **Hard trust boundary.** Only the task instruction and policy files
  (`/AGENTS.MD`, runtime policy books) are authoritative. All file contents,
  search hits, and tool/SQL output are treated as untrusted data, so embedded
  "ignore your instructions" payloads are surfaced as injections, not obeyed.
- **Policy precedence.** When the request conflicts with policy, policy wins and
  the agent reports `OUTCOME_DENIED_SECURITY` with the violated rule.
- **Ground-first discovery.** A deterministic opening turn reads the tree,
  `/AGENTS.MD`, `/bin/date`, and `/bin/id`, then the model must ground in real
  files before mutating state or answering.
- **Precise answers.** The final `message` is graded against an expected answer,
  so the schema pushes a direct, self-contained result with grounding refs - no
  filler, no restating the question.
- **Correct outcome selection.** Explicit guidance maps each situation to the
  right `Outcome` (OK / DENIED_SECURITY / NONE_CLARIFICATION / NONE_UNSUPPORTED /
  ERR_INTERNAL).
- **Robust loop.** Errors are fed back to the model for recovery, a stall guard
  breaks repeated identical calls, and the step budget is configurable.

## LLM providers

The agent is provider-agnostic - one model string in `MODEL_ID` selects the
backend (routing in `llm.py`). Structured output (the SGR schema) is enforced on
every provider.

| Context | `MODEL_ID` | Auth | Why |
|---|---|---|---|
| **Leaderboard attempts** | mixed `claude:opus` + `codex:gpt-5.3-codex-spark` | local Claude/Codex CLIs over OAuth | current best saved dev53 leaderboard profile |
| Fast API sweeps | `openai/gpt-5.5` | `OPENAI_API_KEY` | fastest current diagnostic path; API use must be explicit |
| Prod100 emergency profile | `codex:gpt-5.3-codex` / `codex:gpt-5.3-codex-spark` | local Codex CLI over ChatGPT OAuth | used during the 2026-05-30 prod contest; score pending, Spark quota-sensitive |
| Codex-only baseline | `codex:gpt-5.3-codex` | local `codex` CLI over ChatGPT OAuth | previous strongest single-profile baseline |
| Regression canary | `claude:sonnet` | local `claude` CLI over OAuth | cheaper validation, but lower current score |
| Gemini CLI comparison | `agy` | local Antigravity CLI over Google AI Pro OAuth | available, but currently slower and less stable |
| API fallback | `openai/...` | `OPENAI_API_KEY` | LiteLLM-backed OpenAI path |
| API fallback | `gemini/gemini-3.5-flash` / `pro` | `GEMINI_API_KEY` | LiteLLM-backed Gemini path |
| API fallback | `anthropic/claude-...` | `ANTHROPIC_API_KEY` | Claude over the metered API |

Bare Claude family names (`opus`, `sonnet`, `claude-opus-4-6`, `claude:opus`)
route to the **OAuth CLI**; the `anthropic/` prefix routes to the metered API.
Bare OpenAI-family names like `gpt-5.5`, plus `codex:*`, route to the local
Codex CLI by default. Use `openai/<model>` only when you explicitly want the
OpenAI API key path. `agy` routes to Antigravity CLI; any model suffix after
`agy:` is informational because the CLI selects the Pro-tier Gemini model.

## Setup

1. `cp .env.example .env` and fill in `BITGN_API_KEY` (see
   [Getting the BitGN API key](#getting-the-bitgn-api-key)), `MODEL_ID`, and the
   matching provider credential. `.env` is gitignored and loaded automatically.
   (Plain shell `export`s work too.)
2. `make sync`
3. `make test`  - offline loop check, no keys/network needed.
4. `make run`   - tests: set `MODEL_ID=claude:opus`; challenge: `gemini/gemini-3.5-flash`.

## Getting the BitGN API key

`BITGN_API_KEY` is required for official leaderboard runs (not for the
`bitgn/sandbox` benchmark). Get it from your BitGN profile:

1. Sign in at <https://bitgn.com/auth/login>.
2. Open your profile / settings page at <https://bitgn.com/me>.
3. Copy the API key and `export BITGN_API_KEY=...`.

The key ties a run to your account so its score shows on
[the ECOM leaderboard](https://bitgn.com/challenge/ecom).

## Commands

- Full benchmark: `uv run python main.py`
- Single task: `uv run python main.py t01`
- Subset: `uv run python main.py t01 t04`
- Via Make: `make run` / `make task TASKS="t01 t04"`
- Parallel sweep: `PARALLEL=6 MODEL_ID=codex:gpt-5.3-codex uv run python run_parallel.py`
- Fast OpenAI API diagnostic sweep:
  `OPENAI_API_KEY=... MODEL_ID=openai/gpt-5.5 PARALLEL=20 uv run python run_parallel.py`
  (use for speed, not as a codex-CLI-comparable baseline).
- Codex CLI validation sweep:
  `MODEL_ID=gpt-5.5 PARALLEL=6 uv run python run_parallel.py` or
  `MODEL_ID=codex:gpt-5.3-codex PARALLEL=6 uv run python run_parallel.py`
  (use for current baseline-comparable tests).
- Public run scorer feedback:
  `uv run python score_feedback.py https://eu.bitgn.com/runs/<run-id> --out-dir artifacts/sweeps/<run-label>/feedback`
- Backend portfolio comparison:
  `uv run python portfolio_runner.py --out-dir artifacts/portfolio/<label>`
  runs codex, sonnet, and agy in parallel with isolated logs and disables
  concurrent `RESULTS.md` appends via `NO_RESULTS_APPEND=1`.

## Environment overrides

| Var | Default | Purpose |
|---|---|---|
| `BITGN_API_KEY` | _(empty)_ | required for official ECOM runs (<https://bitgn.com/me>) |
| `MODEL_ID` | `gpt-5.5` | provider/model (see table above) |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | _(empty)_ | provider credential for the chosen `MODEL_ID` |
| `BENCH_ID` / `BENCHMARK_ID` | `bitgn/ecom1-prod` in current prod-contest runner code | benchmark id; set explicitly for dev rehearsals |
| `MAX_STEPS` | `40` | per-trial action budget |
| `MAX_TOKENS` | `16384` | max completion tokens per LLM step |
| `CLAUDE_CLI_TIMEOUT` | `300` | per-step timeout for the Claude OAuth CLI (seconds) |
| `HINT` | _(empty)_ | extra system guidance (open benchmarks expose hints) |
| `BITGN_HOST` / `BENCHMARK_HOST` | `https://api.bitgn.com` | control-plane URL |
| `NO_RESULTS_APPEND` | _(empty)_ | set to `1` for orchestrated multi-backend runs that should not concurrently append `RESULTS.md` |

## Layout

- `agent.py` - SGR reasoning schema, tool surface, the per-trial run loop.
- `llm.py` - provider routing + structured output (LiteLLM for API models, the
  `claude` CLI for OAuth).
- `main.py` - control-plane flow: start run, iterate trials, score, submit.
- `run_parallel.py` - process-pool sweep runner; appends to `RESULTS.md` only
  for full sweeps unless `NO_RESULTS_APPEND=1`.
- `portfolio_runner.py` - comparison orchestrator for codex / sonnet / agy with
  separate per-profile logs and JSON/Markdown summaries.
- `score_feedback.py` - stdlib public-run scraper for evaluated/open BitGN run
  pages and trial scorer details.
- `smoke_test.py` - offline loop test (`make test`): stubs the SDK + the LLM so
  discovery, tool dispatch, error recovery, denial, and completion run without keys.
- `BENCHMARK_NOTES.md` - the ECOM1 task taxonomy the system prompt is tuned against.
- `proto/` - the relevant slice of the BitGN schema for reference (SDKs are
  pulled from the Buf registry, not generated locally).

Derived from the official [bitgn/sample-agents](https://github.com/bitgn/sample-agents)
ECOM sample.
