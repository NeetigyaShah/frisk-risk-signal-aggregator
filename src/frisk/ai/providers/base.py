"""Provider boundary — the ONLY LLM abstraction the rest of the code imports.

Swapping NVIDIA ↔ Gemini ↔ Claude ↔ mock is a one-line config change; nothing outside this package
knows which model answered. Each provider exposes a structured `complete()` (single call) and an
optional `chat_model()` (a LangChain chat model for the multi-step graph).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class Provider(ABC):
    name: str = "base"

    @abstractmethod
    def available(self) -> bool:
        """True if this provider can be called (key present, SDK importable)."""

    @abstractmethod
    def complete(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        """Return a validated instance of `schema` (structured output). May raise; the caller degrades."""

    def chat_model(self):
        """A LangChain BaseChatModel for the LangGraph orchestration, or None if unsupported."""
        return None
