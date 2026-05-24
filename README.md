# BitGN ECOM Agent (SGR)

A competitive Python agent for the [BitGN](https://bitgn.com) `bitgn/ecom1-dev`
benchmark (Agentic E-commerce challenge). Leaderboard:
[bitgn.com/challenge/ecom](https://bitgn.com/challenge/ecom).

It talks to the `bitgn.vm.ecom` runtime (a file-shaped ecommerce OS plus runtime
tools such as `/bin/sql`) over the schema published at
[buf.build/bitgn/api](https://buf.build/bitgn/api), and drives an LLM with
[Schema-Guided Reasoning](https://abdullin.com/schema-guided-reasoning/).

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

## Setup

1. Export `BITGN_API_KEY` (get it at <https://bitgn.com/me>) - required for
   official leaderboard runs.
2. Export `OPENAI_API_KEY` (or point the OpenAI client at another provider via
   `OPENAI_BASE_URL`).
3. `make sync`
4. `make run`

## Commands

- Full benchmark: `uv run python main.py`
- Single task: `uv run python main.py t01`
- Subset: `uv run python main.py t01 t04`
- Via Make: `make run` / `make task TASKS="t01 t04"`

## Environment overrides

| Var | Default | Purpose |
|---|---|---|
| `BITGN_API_KEY` | _(empty)_ | required for official ECOM runs |
| `OPENAI_API_KEY` | _(empty)_ | LLM provider key |
| `MODEL_ID` | `gpt-5.4` | reasoning model; e.g. `gpt-4.1-2025-04-14` for a cheaper run |
| `BENCH_ID` / `BENCHMARK_ID` | `bitgn/ecom1-dev` | benchmark id |
| `MAX_STEPS` | `40` | per-trial action budget |
| `HINT` | _(empty)_ | extra system guidance (open benchmarks expose hints) |
| `BITGN_HOST` / `BENCHMARK_HOST` | `https://api.bitgn.com` | control-plane URL |

## Layout

- `agent.py` - SGR reasoning schema, tool surface, the per-trial run loop.
- `main.py` - control-plane flow: start run, iterate trials, score, submit.
- `proto/` - the relevant slice of the BitGN schema for reference (SDKs are
  pulled from the Buf registry, not generated locally).

Derived from the official [bitgn/sample-agents](https://github.com/bitgn/sample-agents)
ECOM sample.
