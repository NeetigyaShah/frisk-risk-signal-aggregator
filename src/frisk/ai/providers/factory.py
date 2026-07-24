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


def get_provider(name: str | None = None) -> Provider:
    name = name or settings.provider
    if name not in _cache:
        _cache[name] = _REGISTRY.get(name, MockProvider)()
    return _cache[name]
