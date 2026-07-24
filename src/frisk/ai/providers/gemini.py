"""Google Gemini provider (google-genai native structured output)."""
from __future__ import annotations

from pydantic import BaseModel

from frisk.config import CONFIG, settings
from frisk.ai.providers.base import Provider

_LLM = CONFIG["llm"]


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self):
        self._c = None

    def available(self) -> bool:
        return bool(settings.gemini_api_key or settings.google_api_key)

    def _client(self):
        if self._c is None:
            from google import genai
            self._c = genai.Client(api_key=settings.gemini_api_key or settings.google_api_key)
        return self._c

    def complete(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        from google.genai import types
        resp = self._client().models.generate_content(
            model=_LLM["gemini_model"], contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=schema,
                temperature=_LLM["temperature"]),
        )
        return resp.parsed or schema.model_validate_json(resp.text)
