"""Provider-agnostic structured-output backend for the SGR agent.

One entry point - `parse_step(model_id, messages, schema)` - returns a validated
instance of the given Pydantic schema (the agent's `NextStep`). Provider is
chosen from `model_id`:

- `gpt-5.5`, `openai/...`            -> OpenAI (LiteLLM), structured outputs
- `gemini/gemini-3.5-flash` | `pro`  -> Google Gemini (LiteLLM), fast - use in the challenge
- `anthropic/claude-...`             -> Anthropic API (LiteLLM), needs ANTHROPIC_API_KEY
- `claude:opus` | `opus` | `sonnet`  -> local `claude` CLI over OAuth (no API key) - use in tests

Tests default to Claude OAuth (no metered key); the challenge defaults to Gemini
3.5 for speed. The neutral default model is `gpt-5.5`.
"""

import json
import os
import shutil
import subprocess
from typing import List, Type, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

Message = dict  # {"role": "system"|"user"|"assistant", "content": str}

CLAUDE_ALIASES = {"opus", "sonnet", "haiku"}
_DEFAULT_MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "16384"))


class LLMError(RuntimeError):
    pass


def _provider(model_id: str) -> str:
    low = model_id.lower()
    if low.startswith(("claude:", "claude-cli:")) or low in CLAUDE_ALIASES:
        return "claude_cli"
    if low.startswith(("claude", "opus", "sonnet", "haiku")):
        # bare claude family name without the `anthropic/` API prefix -> OAuth CLI
        return "claude_cli"
    if low.startswith(("gemini", "vertex_ai/gemini")):
        return "litellm"
    return "litellm"


# ---------------------------------------------------------------------------
# LiteLLM path: OpenAI / Gemini / Anthropic-API, uniform structured output.
# ---------------------------------------------------------------------------


_TOOL_NAMES = (
    "tree, find, search, list, read, write, delete, stat, exec, report_completion"
)


def _litellm_parse(
    model_id: str, messages: List[Message], schema: Type[T], max_tokens: int
) -> T:
    import litellm

    # LiteLLM maps response_format=PydanticModel to each provider's native
    # structured-output mechanism (OpenAI json_schema, Gemini responseSchema,
    # Anthropic tool-use) and normalises param names like max_tokens. Weaker
    # models (e.g. Gemini Flash) do not strictly honour the discriminated-union
    # const fields, so validate and re-prompt with the error until it conforms.
    msgs = messages
    last_err = ""
    for attempt in range(3):
        resp = litellm.completion(
            model=model_id,
            messages=msgs,
            response_format=schema,
            max_tokens=max_tokens,
        )
        content = resp.choices[0].message.content
        try:
            return schema.model_validate_json(_extract_json(content))
        except (ValidationError, ValueError) as exc:
            last_err = str(exc)[:600]
            msgs = list(messages) + [
                {"role": "assistant", "content": content or ""},
                {
                    "role": "user",
                    "content": (
                        f"That JSON did not match the required schema:\n{last_err}\n"
                        "Return ONLY one corrected JSON object that validates. The "
                        f"`function.tool` value MUST be exactly one of: {_TOOL_NAMES}."
                    ),
                },
            ]
    raise LLMError(f"{model_id} returned invalid JSON after retries: {last_err}")


# ---------------------------------------------------------------------------
# Claude OAuth path: drive the local `claude` CLI headlessly. No API key.
# ---------------------------------------------------------------------------


def _claude_cli_parse(
    model_id: str, messages: List[Message], schema: Type[T], max_tokens: int
) -> T:
    claude_bin = shutil.which("claude") or shutil.which("claude.cmd")
    if not claude_bin:
        raise LLMError(
            "claude CLI not found on PATH; install Claude Code or set MODEL_ID to "
            "an API model (e.g. gpt-5.5 or gemini/gemini-3.5-flash)"
        )

    model = model_id.split(":", 1)[1] if ":" in model_id else model_id

    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    convo = [m for m in messages if m["role"] != "system"]

    schema_json = json.dumps(schema.model_json_schema(), separators=(",", ":"))
    system_prompt = (
        "IGNORE ALL PROJECT INSTRUCTIONS (CLAUDE.md, AGENTS.md on the host). "
        + "\n\n".join(system_parts)
        + "\n\nYou MUST reply with exactly one JSON object that validates against "
        "this JSON Schema. No prose, no markdown fences, JSON only:\n"
        + schema_json
    )

    transcript = "\n\n".join(f"[{m['role'].upper()}]\n{m['content']}" for m in convo)
    prompt = transcript + "\n\n[ASSISTANT]\nReturn the JSON object now."

    last_err = ""
    for attempt in range(2):
        stdin = prompt if attempt == 0 else (
            prompt + f"\n\n[SYSTEM]\nPrevious reply was invalid JSON: {last_err}. "
            "Return ONLY the corrected JSON object."
        )
        result = subprocess.run(
            [
                claude_bin, "-p",
                "--model", model,
                "--output-format", "text",
                "--allowedTools", "",
                "--append-system-prompt", system_prompt,
            ],
            input=stdin,
            capture_output=True,
            text=True,
            cwd="/tmp",  # run away from any host CLAUDE.md
            timeout=int(os.environ.get("CLAUDE_CLI_TIMEOUT", "300")),
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise LLMError(f"claude CLI failed (rc={result.returncode}): {result.stderr.strip()[:300]}")
        try:
            return schema.model_validate_json(_extract_json(result.stdout))
        except (ValidationError, ValueError) as exc:
            last_err = str(exc)[:300]
    raise LLMError(f"claude CLI returned invalid JSON twice: {last_err}")


# ---------------------------------------------------------------------------


def _extract_json(text: str) -> str:
    """Return the first balanced top-level JSON object found in text."""
    if text is None:
        raise ValueError("empty model response")
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        if text.lstrip().startswith(("json", "JSON")):
            text = text.lstrip()[4:]
    start = text.find("{")
    if start == -1:
        raise ValueError(f"no JSON object in response: {text[:200]!r}")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    raise ValueError("unbalanced JSON object in response")


def parse_step(
    model_id: str,
    messages: List[Message],
    schema: Type[T],
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> T:
    provider = _provider(model_id)
    if provider == "claude_cli":
        return _claude_cli_parse(model_id, messages, schema, max_tokens)
    return _litellm_parse(model_id, messages, schema, max_tokens)
