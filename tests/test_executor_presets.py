from __future__ import annotations

import pytest

from aicmo.adapters import CommandAdapter
from aicmo.anthropic_adapter import AnthropicAdapter
from aicmo.cli import adapter_for_executor
from aicmo.errors import AicmoError


def test_preset_claude() -> None:
    adapter = adapter_for_executor("claude")
    assert isinstance(adapter, CommandAdapter)
    assert adapter.command == ("claude", "-p")


def test_preset_codex() -> None:
    adapter = adapter_for_executor("codex")
    assert isinstance(adapter, CommandAdapter)
    assert adapter.command == ("codex", "exec")


def test_preset_local_and_none_are_default() -> None:
    assert adapter_for_executor("local") is None
    assert adapter_for_executor(None) is None
    assert adapter_for_executor("") is None


def test_preset_anthropic() -> None:
    assert isinstance(adapter_for_executor("anthropic"), AnthropicAdapter)


def test_preset_unknown_raises() -> None:
    with pytest.raises(AicmoError):
        adapter_for_executor("bogus")
