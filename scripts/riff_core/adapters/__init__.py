"""Harness adapters bundled with Riff."""

from .base import HarnessAdapter
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .hermes import HermesAdapter
from .pi import PiAdapter


def adapter_registry() -> dict[str, HarnessAdapter]:
    adapters: list[HarnessAdapter] = [
        ClaudeAdapter(),
        CodexAdapter(),
        PiAdapter(),
        HermesAdapter(),
    ]
    return {adapter.name: adapter for adapter in adapters}


__all__ = ["HarnessAdapter", "adapter_registry"]
