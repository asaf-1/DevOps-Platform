"""The one place that knows which model provider is in use.

MODEL_PROVIDER=ollama   -> Ollama's OpenAI-compatible endpoint at OLLAMA_BASE_URL
MODEL_PROVIDER=anthropic -> Anthropic's API with ANTHROPIC_API_KEY
MODEL_NAME names the model on that provider. Nothing else in the runtime
imports a provider class.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from pydantic_ai.models import Model

DEFAULTS = {
    "ollama": "qwen3:4b",
    "anthropic": "claude-sonnet-5-5",
}


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    name: str
    ollama_base_url: str = "http://localhost:11434"

    @classmethod
    def from_env(cls) -> ModelConfig:
        provider = os.environ.get("MODEL_PROVIDER", "ollama").strip().lower()
        if provider not in DEFAULTS:
            raise ValueError(f"MODEL_PROVIDER must be one of {sorted(DEFAULTS)}, got {provider!r}")
        return cls(
            provider=provider,
            name=os.environ.get("MODEL_NAME") or DEFAULTS[provider],
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL", cls.ollama_base_url).rstrip("/"),
        )


def build_model(cfg: ModelConfig | None = None) -> Model:
    """A Pydantic AI model for the configured provider."""
    cfg = cfg or ModelConfig.from_env()
    if cfg.provider == "ollama":
        from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
        from pydantic_ai.providers.ollama import OllamaProvider

        # A CPU model needs a long request timeout (one step can take minutes
        # of prompt processing) and no thinking block before each tool call.
        settings = OpenAIChatModelSettings(
            timeout=float(os.environ.get("MODEL_REQUEST_TIMEOUT", "900")),
            extra_body={"think": False},
        )
        return OpenAIChatModel(
            cfg.name,
            provider=OllamaProvider(base_url=f"{cfg.ollama_base_url}/v1"),
            settings=settings,
        )
    if cfg.provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ValueError("MODEL_PROVIDER=anthropic needs ANTHROPIC_API_KEY")
        from pydantic_ai.models.anthropic import AnthropicModel

        return AnthropicModel(cfg.name)
    raise ValueError(cfg.provider)
