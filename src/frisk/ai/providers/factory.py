"""Provider factory — one place that maps a config name to a provider singleton."""
from __future__ import annotations

from frisk.config import settings
from frisk.ai.providers.anthropic import AnthropicProvider
from frisk.ai.providers.base import Provider
from frisk.ai.providers.gemini import GeminiProvider
from frisk.ai.providers.mock import MockProvider
from frisk.ai.providers.nvidia import NvidiaProvider
from frisk.ai.providers.openrouter import OpenRouterProvider

_REGISTRY = {
    "openrouter": OpenRouterProvider,
    "nvidia": NvidiaProvider,
    "gemini": GeminiProvider,
    "anthropic": AnthropicProvider,
    "mock": MockProvider,
}

_cache: dict[str, Provider] = {}
_warned: set[str] = set()


def get_provider(name: str | None = None) -> Provider:
    """Resolve the configured provider, falling back to mock if it has no usable key.

    `settings.provider` defaults to "openrouter" regardless of whether a key is actually
    configured — that default exists so a real key "just works" once added, but it means an
    unconfigured install previously tried OpenRouter anyway, raised OpenAIError on every single
    call, and (via the caller's blanket except-and-continue) silently scored zero customers. The
    README's central claim — "no key needed, runs on the mock provider out of the box" — was true
    only for `frisk score --offline`, which sets FRISK_PROVIDER=mock explicitly; `frisk serve`, the
    command the setup script itself prints as the next step, had no such override and was broken
    on a completely fresh install with a blank .env. This is that fallback, in the one place every
    entrypoint shares.
    """
    name = name or settings.provider
    if name not in _cache:
        inst = _REGISTRY.get(name, MockProvider)()
        if name != "mock" and not inst.available():
            if name not in _warned:
                print(f"! provider '{name}' has no API key configured — using the mock provider instead")
                _warned.add(name)
            inst = MockProvider()
        _cache[name] = inst
    return _cache[name]
