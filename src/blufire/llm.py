"""Anthropic client wrapper + robust JSON extractor.

The ``extract_json`` function replaces the fragile ``raw.find('{')`` /
``raw.rfind('}')`` patterns that previously appeared in four scripts: it
handles raw JSON, markdown-fenced JSON, and prose-wrapped JSON without
truncating mid-object.
"""

from __future__ import annotations

import json
import re
from typing import Any

import anthropic
import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from blufire.logging_setup import get_logger
from blufire.settings import Settings

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


class LLMOutputError(ValueError):
    """Raised when Claude output cannot be parsed as JSON."""


def _scan_balanced(text: str, start: int) -> int | None:
    """Return index AFTER the closing brace of a balanced ``{...}`` starting at ``text[start]``,
    or None if no balanced object exists. Tracks string state and escape state.
    """
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


def extract_json(raw: str) -> Any:
    """Parse ``raw`` as JSON, tolerating prose wrappers and markdown fences.

    Strategy:
    1. ``json.loads`` raw.
    2. If raw contains a ```` ``` ```` fence, try each fenced block.
    3. Walk the string brace-by-brace (string-aware) and return the first
       balanced ``{...}`` that parses.
    4. Raise :class:`LLMOutputError` with the truncated payload.
    """
    if raw is None:
        raise LLMOutputError("LLM returned None")

    candidates: list[str] = [raw.strip()]
    candidates.extend(m.group(1).strip() for m in _FENCE_RE.finditer(raw))

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    for i, ch in enumerate(raw):
        if ch != "{":
            continue
        end = _scan_balanced(raw, i)
        if end is None:
            continue
        try:
            return json.loads(raw[i:end])
        except json.JSONDecodeError:
            continue

    # Show both ends so the offending region near the truncation boundary
    # doesn't get hidden when the output is large.
    if len(raw) <= 1000:
        snippet = raw
    else:
        snippet = f"{raw[:500]} ...[{len(raw) - 1000} chars elided]... {raw[-500:]}"
    raise LLMOutputError(f"could not extract JSON from LLM output: {snippet!r}")


_RETRYABLE = (
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


def build_client(settings: Settings) -> anthropic.Anthropic:
    """Build an Anthropic client with explicit timeouts. Raises if API key missing."""
    if settings.secrets.anthropic_api_key is None:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured. " "Add it to your .env (see .env.example)."
        )
    return anthropic.Anthropic(
        api_key=settings.secrets.anthropic_api_key.get_secret_value(),
        timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0),
        max_retries=0,  # we own retries via tenacity below
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2.0, max=30.0),
    retry=retry_if_exception_type(_RETRYABLE),
    reraise=True,
)
def complete(
    client: anthropic.Anthropic,
    *,
    model: str,
    prompt: str,
    max_tokens: int = 1024,
    system: str | None = None,
    temperature: float = 0.7,
) -> str:
    """One-shot text completion. Retries on transient API errors."""
    log = get_logger("blufire.llm").bind(model=model, max_tokens=max_tokens)
    log.debug("anthropic_call_start")
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    msg = client.messages.create(**kwargs)
    text = "".join(block.text for block in msg.content if hasattr(block, "text"))
    log.debug("anthropic_call_done", chars=len(text))
    return text


def complete_json(
    client: anthropic.Anthropic,
    *,
    model: str,
    prompt: str,
    max_tokens: int = 1024,
    system: str | None = None,
    temperature: float = 0.7,
) -> Any:
    """Convenience: call ``complete`` and parse its output via ``extract_json``."""
    raw = complete(
        client,
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        system=system,
        temperature=temperature,
    )
    return extract_json(raw)
