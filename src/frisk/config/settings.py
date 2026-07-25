"""Environment-configurable settings (pydantic-settings).

Everything that changes per environment/deployment — LLM provider + models, scale knobs, API keys —
binds from env (prefix ``FRISK_``) or ``.env``, with safe defaults so the app runs offline out of the
box. Provider API keys are read WITHOUT the prefix (e.g. ``NVIDIA_API_KEY``) and never committed.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from frisk.paths import ENV_FILE


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FRISK_", env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore",
    )

    # --- LLM behaviour ---
    provider: str = "openrouter"           # openrouter | nvidia | gemini | anthropic | mock
    # OpenRouter (OpenAI-compatible) — deepseek-v4-flash, preferring Baidu Qianfan (fastest) with fast fallbacks
    openrouter_model: str = "deepseek/deepseek-v4-flash"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_extra_body: dict = Field(default_factory=lambda: {
        "provider": {"order": ["baidu", "alibaba", "deepinfra", "fireworks"], "allow_fallbacks": True}})
    nvidia_model: str = "deepseek-ai/deepseek-v4-flash"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_extra_body: dict = Field(
        default_factory=lambda: {"chat_template_kwargs": {"thinking": False, "reasoning_effort": "low"}})
    gemini_model: str = "gemini-2.5-flash-lite"
    anthropic_model: str = "claude-haiku-4-5-20251001"
    temperature: float = 0.0
    max_tokens: int = 8192
    max_retries: int = 3
    timeout_s: int = 60

    # --- human-in-the-loop ---
    confidence_threshold: float = 0.60     # below this the agent is "unsure" -> route to the human review queue
    redis_url: str = "redis://localhost:6379/0"   # review-queue broker + working-memory scratchpad

    # --- scale / throughput ---
    workers: int = 16                      # parallel workers (across customers) for batch scoring
    llm_concurrency: int = 24              # max simultaneous in-flight LLM calls app-wide. Measured:
                                            # 4 concurrent calls finish in the same wall-clock as 1
                                            # (no OpenRouter throttling on this key), so this is a
                                            # safety backstop against runaway fan-out, NOT a throttle.

    # --- agentic scorer + layered memory ---
    agent_max_steps: int = 10              # max tool-calling turns before the orchestrator must finalize.
                                            # Measured at ~3.6s per round-trip, so this is the single
                                            # biggest lever on latency — but it is NOT free to shrink.
                                            # 8 was retried after adding the pre-loaded briefing, the
                                            # finalize-only binding and the duplicate-result guard, and
                                            # STILL failed: the agent spent all 8 on lookups and never
                                            # reached finalize -> PENDING_REVIEW at confidence 0, which
                                            # is a worse outcome than a slower correct answer.
                                            # 10 finalizes reliably; the real saving came from the
                                            # duplicate-result guard, not from squeezing this number.
    scratchpad_ttl_s: int = 3600           # Redis working-memory TTL backstop (evicted explicitly on every exit)
    memory_topk: int = 3                   # per-customer history + similar-case retrieval depth

    # --- provider keys (read WITHOUT the FRISK_ prefix; keep out of git) ---
    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    nvidia_api_key: str | None = Field(default=None, validation_alias="NVIDIA_API_KEY")
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    google_api_key: str | None = Field(default=None, validation_alias="GOOGLE_API_KEY")
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")


settings = Settings()
