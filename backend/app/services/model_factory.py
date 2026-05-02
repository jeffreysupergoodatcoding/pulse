"""
Model factory for the multi-provider experiment.

Returns a CAMEL ModelBackend + an OpenAI-compatible client for a given provider.
The provider determines which LLM drives agent decisions inside OASIS.

Providers:
  - "gemini"    → Google Gemini (default; cheap, fast)
  - "openai"    → OpenAI (gpt-4o-mini default)
  - "anthropic" → Anthropic Claude (sonnet-4-5 default)

Used by run_parallel_simulation.py via the --llm_provider CLI flag.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from camel.models import ModelFactory as CamelModelFactory
from camel.types import ModelPlatformType
from openai import OpenAI


@dataclass
class ProviderSpec:
    provider: str           # canonical name: gemini | openai | anthropic
    model_name: str         # human-readable model id used in logs/results
    camel_model: object     # CAMEL ModelBackend instance for OASIS
    llm_client: OpenAI      # OpenAI-compatible client for non-agent calls (sentiment, scratch)
    api_key: str
    base_url: str | None


_DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash-lite",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5-20250929",
}

_OPENAI_COMPAT_BASE = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openai": "https://api.openai.com/v1",
    # Anthropic does not expose an OpenAI-compatible chat endpoint by default;
    # OpenAI-style scratch calls (sentiment scoring etc.) for the Anthropic run
    # fall back to Gemini so we don't conflate scratch-LLM with agent-LLM.
}


def build_provider(provider: str, model_name: str | None = None) -> ProviderSpec:
    """Build a ProviderSpec for the given provider name."""
    provider = (provider or "gemini").lower().strip()
    if provider not in _DEFAULT_MODELS:
        raise ValueError(f"Unknown provider: {provider!r}. Use one of {list(_DEFAULT_MODELS)}")

    model_name = model_name or _DEFAULT_MODELS[provider]

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY", "")
        base_url = _OPENAI_COMPAT_BASE["gemini"]
        camel_model = CamelModelFactory.create(
            model_platform=ModelPlatformType.GEMINI,
            model_type=model_name,
            api_key=api_key,
        )
        client = OpenAI(api_key=api_key, base_url=base_url)

    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set in env")
        base_url = _OPENAI_COMPAT_BASE["openai"]
        camel_model = CamelModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type=model_name,
            api_key=api_key,
            url=base_url,
        )
        client = OpenAI(api_key=api_key, base_url=base_url)

    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in env")
        camel_model = CamelModelFactory.create(
            model_platform=ModelPlatformType.ANTHROPIC,
            model_type=model_name,
            api_key=api_key,
        )
        # Scratch client for non-agent LLM calls reuses Gemini (cheaper, faster)
        # so the variable under test is strictly the agent decision LLM.
        scratch_key = os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY", "")
        client = OpenAI(api_key=scratch_key, base_url=_OPENAI_COMPAT_BASE["gemini"])
        base_url = None

    else:
        raise ValueError(f"Unhandled provider: {provider}")

    return ProviderSpec(
        provider=provider,
        model_name=model_name,
        camel_model=camel_model,
        llm_client=client,
        api_key=api_key,
        base_url=base_url,
    )
