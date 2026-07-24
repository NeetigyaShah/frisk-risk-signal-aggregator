"""Anthropic Claude provider (instructor + anthropic)."""
from __future__ import annotations

from pydantic import BaseModel

from frisk.config import CONFIG, settings
from frisk.ai.providers.base import Provider

_LLM = CONFIG["llm"]


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self):
        self._ic = None

    def available(self) -> bool:
        return bool(settings.anthropic_api_key)

    def _instructor(self):
        if self._ic is None:
            import instructor
            from anthropic import Anthropic
            self._ic = instructor.from_anthropic(Anthropic())
        return self._ic

    def complete(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        return self._instructor().chat.completions.create(
            model=_LLM["model"], max_tokens=1024, temperature=_LLM["temperature"],
            max_retries=_LLM["max_retries"], response_model=schema,
            messages=[{"role": "user", "content": prompt}],
        )
