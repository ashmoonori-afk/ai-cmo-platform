from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from typing import Protocol

from aicmo.adapters import AgentRequest, AgentResult, compose_prompt

_MODEL_ALIASES = {
    "opus": "claude-opus-4-8",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
    "fable": "claude-fable-5",
}
_DEFAULT_MODEL = "sonnet"
_MAX_TOKENS = 2048
_DETAIL_LIMIT = 300


def resolve_model(alias: str, default: str = _DEFAULT_MODEL) -> str:
    key = (alias or default).strip()
    if key in _MODEL_ALIASES:
        return _MODEL_ALIASES[key]
    if key.startswith("claude-"):
        return key
    return _MODEL_ALIASES.get(default, default)


class _Block(Protocol):
    text: str


class _Response(Protocol):
    content: list[_Block]


class _Messages(Protocol):
    def create(self, **kwargs: object) -> _Response: ...


class _Client(Protocol):
    messages: _Messages


def _make_client() -> _Client | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    if importlib.util.find_spec("anthropic") is None:
        return None
    module = importlib.import_module("anthropic")
    factory_name = "Anthropic"
    factory = getattr(module, factory_name)
    return factory()


@dataclass(frozen=True, slots=True)
class AnthropicAdapter:
    """Live adapter calling the Anthropic Messages API. Degrades gracefully.

    Without ANTHROPIC_API_KEY or the `anthropic` SDK (and no injected client), generate
    returns an ok=False 'unavailable: ...' status — it never raises. The per-step model
    (request.model) is resolved from an alias (opus/sonnet/haiku/fable) or a full id.
    """

    default_model: str = _DEFAULT_MODEL
    max_tokens: int = _MAX_TOKENS
    client: _Client | None = None

    def generate(self, request: AgentRequest) -> AgentResult:
        client = self.client or _make_client()
        if client is None:
            return AgentResult(
                text="",
                ok=False,
                detail="unavailable: set ANTHROPIC_API_KEY and `uv add anthropic`",
            )
        model = resolve_model(request.model, self.default_model)
        prompt = compose_prompt(request)
        try:
            response = client.messages.create(
                model=model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(block.text for block in response.content).strip()
        except Exception as exc:  # noqa: BLE001 — any SDK/network error becomes a status, never a crash
            detail = f"unavailable: anthropic error: {str(exc)[:_DETAIL_LIMIT]}"
            return AgentResult(text="", ok=False, detail=detail)
        if not text:
            return AgentResult(text="", ok=False, detail="unavailable: empty model response")
        return AgentResult(text=text, ok=True)
