"""LLM provider boundary."""
from frisk.ai.providers.base import Provider
from frisk.ai.providers.factory import get_provider

__all__ = ["Provider", "get_provider"]
