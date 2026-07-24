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
    llm_mode: str = "auto"                 # auto -> real if a key is set else simulated; off -> rules-only
    provider: str = "nvidia"               # nvidia | gemini | anthropic | mock
    multi_step: bool = True                # LangGraph 5-step orchestration vs single call
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

    # --- scale / throughput ---
    workers: int = 16                      # parallel workers for I/O-bound cross-checks
    crosscheck_policy: str = "all"         # all -> LLM on everyone; gated -> LLM only on the MED band
    gated_confidence: float = 0.85         # confidence when rules are policy-authoritative (LLM gated out)

    # --- provider keys (read WITHOUT the FRISK_ prefix; keep out of git) ---
    nvidia_api_key: str | None = Field(default=None, validation_alias="NVIDIA_API_KEY")
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    google_api_key: str | None = Field(default=None, validation_alias="GOOGLE_API_KEY")
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")


settings = Settings()
