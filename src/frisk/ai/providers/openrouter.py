"""OpenRouter provider (OpenAI-compatible) — deepseek-v4-flash, preferring Baidu Qianfan for throughput.

`extra_body.provider` pins the routing order (Baidu → Alibaba → DeepInfra → Fireworks, with fallbacks),
so we get the fastest available endpoint. Same class serves both the single call (instructor) and the
LangGraph multi-step graph (ChatOpenAI).
"""
from __future__ import annotations

from pydantic import BaseModel

from frisk.config import CONFIG, settings
from frisk.ai.providers.base import Provider

_LLM = CONFIG["llm"]


class OpenRouterProvider(Provider):
    name = "openrouter"

    def __init__(self):
        self._ic = None
        self._chat = None

    def available(self) -> bool:
        return bool(settings.openrouter_api_key)

    def _instructor(self):
        if self._ic is None:
            import instructor
            from openai import OpenAI
            base = OpenAI(base_url=_LLM["openrouter_base_url"], api_key=settings.openrouter_api_key)
            self._ic = instructor.from_openai(base, mode=instructor.Mode.JSON)
        return self._ic

    def complete(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        return self._instructor().chat.completions.create(
            model=_LLM["openrouter_model"], max_tokens=_LLM["max_tokens"], temperature=_LLM["temperature"],
            response_model=schema, messages=[{"role": "user", "content": prompt}],
            extra_body=_LLM.get("openrouter_extra_body", {}),
        )

    def chat_model(self):
        if self._chat is None:
            from langchain_openai import ChatOpenAI
            self._chat = ChatOpenAI(
                model=_LLM["openrouter_model"], base_url=_LLM["openrouter_base_url"],
                api_key=settings.openrouter_api_key, temperature=_LLM["temperature"],
                max_tokens=_LLM["max_tokens"], timeout=_LLM["timeout_s"], max_retries=_LLM["max_retries"],
                extra_body=_LLM.get("openrouter_extra_body", {}),
            )
        return self._chat
