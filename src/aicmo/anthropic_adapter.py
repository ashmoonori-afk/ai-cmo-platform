from __future__ import annotations

import importlib.util
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from aicmo.adapters import AgentRequest, AgentResult, GenerationUsage, compose_prompt
from aicmo.errors import AicmoError
from aicmo.redaction import redact

_MODEL_ALIASES: Final = {
    "opus": "claude-opus-4-8",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
    "fable": "claude-fable-5",
    "claude-opus-4-8": "claude-opus-4-8",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
    "claude-fable-5": "claude-fable-5",
}
_DEFAULT_MODEL = "sonnet"
_MAX_TOKENS = 2048
_DETAIL_LIMIT = 300


def resolve_model(alias: str, default: str = _DEFAULT_MODEL) -> str:
    key = alias.strip() or default.strip()
    try:
        return _MODEL_ALIASES[key]
    except KeyError:
        allowed = ", ".join(sorted(_MODEL_ALIASES))
        msg = f"unknown Anthropic model alias {key!r}; expected one of: {allowed}"
        raise AicmoError(msg) from None


class _Response(Protocol):
    @property
    def content(self) -> Sequence[object]: ...

    @property
    def stop_reason(self) -> str | None: ...

    @property
    def usage(self) -> object: ...

    @property
    def model(self) -> str: ...


class _Messages(Protocol):
    def create(self, **kwargs: object) -> _Response: ...


class _Client(Protocol):
    @property
    def messages(self) -> _Messages: ...


def _make_client() -> _Client | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    if importlib.util.find_spec("anthropic") is None:
        return None
    module = importlib.import_module("anthropic")
    factory_name = "Anthropic"
    factory = getattr(module, factory_name)
    return factory()


def _token_count(usage: object, name: str) -> int | None:
    value: object = getattr(usage, name, None)
    return value if type(value) is int and value >= 0 else None


def _response_usage(response: _Response, requested_model: str) -> GenerationUsage:
    reason = response.stop_reason
    known_reasons = {
        "end_turn",
        "max_tokens",
        "model_context_window_exceeded",
        "stop_sequence",
        "tool_use",
        "pause_turn",
        "refusal",
    }
    model = response.model
    return GenerationUsage(
        provider="anthropic",
        requested_model=requested_model,
        response_model=model if re.fullmatch(r"claude-[a-zA-Z0-9.-]{1,100}", model) else None,
        stop_reason=reason if reason in known_reasons else "unavailable",
        input_tokens=_token_count(response.usage, "input_tokens"),
        output_tokens=_token_count(response.usage, "output_tokens"),
        cache_creation_input_tokens=_token_count(response.usage, "cache_creation_input_tokens"),
        cache_read_input_tokens=_token_count(response.usage, "cache_read_input_tokens"),
    )


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
        model = resolve_model(request.model, self.default_model)
        usage = GenerationUsage(provider="anthropic", requested_model=model)
        try:
            client = self.client or _make_client()
        except Exception as exc:  # noqa: BLE001 — SDK construction errors become a status, never a crash
            detail = redact(f"unavailable: anthropic client error: {str(exc)[:_DETAIL_LIMIT]}")
            return AgentResult(text="", ok=False, detail=detail, usage=usage)
        if client is None:
            return AgentResult(
                text="",
                ok=False,
                detail="unavailable: set ANTHROPIC_API_KEY and `uv add anthropic`",
                usage=usage,
            )
        prompt = compose_prompt(request)
        try:
            response = client.messages.create(
                model=model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            usage = _response_usage(response, model)
            if usage.stop_reason != "end_turn":
                return AgentResult(
                    text="",
                    ok=False,
                    usage=usage,
                    detail=f"incomplete model response: stop_reason={usage.stop_reason}",
                )
            texts: list[str] = []
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    text_value: object = getattr(block, "text", None)
                    if isinstance(text_value, str):
                        texts.append(text_value)
            text = "".join(texts).strip()
        except Exception as exc:  # noqa: BLE001 — any SDK/network error becomes a status, never a crash
            detail = redact(f"unavailable: anthropic error: {str(exc)[:_DETAIL_LIMIT]}")
            return AgentResult(text="", ok=False, detail=detail, usage=usage)
        if not text:
            return AgentResult(
                text="",
                ok=False,
                detail="unavailable: empty model response",
                usage=usage,
            )
        return AgentResult(text=text, ok=True, usage=usage)
