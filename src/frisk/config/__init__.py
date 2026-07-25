"""Config package. Exposes the assembled ``CONFIG`` (domain constants + env-bound LLM/scale) plus the
band helpers, so call sites use ``from frisk.config import CONFIG, band_for``.
"""
from __future__ import annotations

# Populate os.environ from .env too, for libraries that read env vars directly (google-genai, langsmith).
try:
    from dotenv import load_dotenv

    from frisk.paths import ENV_FILE
    load_dotenv(str(ENV_FILE))
except Exception:
    pass

from frisk.config.constants import CONFIG as _DOMAIN, band_for, BAND_LABEL, LABEL_BAND  # noqa: E402
from frisk.config.settings import settings  # noqa: E402

# Assemble the runtime CONFIG: domain policy + env-bound sections (back-compat shape for all modules).
CONFIG = dict(_DOMAIN)
CONFIG["llm"] = {
    "provider": settings.provider,
    "openrouter_model": settings.openrouter_model,
    "openrouter_base_url": settings.openrouter_base_url,
    "openrouter_extra_body": settings.openrouter_extra_body,
    "nvidia_model": settings.nvidia_model,
    "nvidia_base_url": settings.nvidia_base_url,
    "nvidia_extra_body": settings.nvidia_extra_body,
    "gemini_model": settings.gemini_model,
    "model": settings.anthropic_model,
    "temperature": settings.temperature,
    "max_tokens": settings.max_tokens,
    "max_retries": settings.max_retries,
    "timeout_s": settings.timeout_s,
}
CONFIG["scale"] = {"workers": settings.workers}
CONFIG["confidence_threshold"] = settings.confidence_threshold
CONFIG["redis_url"] = settings.redis_url
# agentic scorer + layered memory knobs
CONFIG["agent_max_steps"] = settings.agent_max_steps
CONFIG["llm_concurrency"] = settings.llm_concurrency
CONFIG["scratchpad_ttl_s"] = settings.scratchpad_ttl_s
CONFIG["memory_topk"] = settings.memory_topk

__all__ = ["CONFIG", "band_for", "BAND_LABEL", "LABEL_BAND", "settings"]
