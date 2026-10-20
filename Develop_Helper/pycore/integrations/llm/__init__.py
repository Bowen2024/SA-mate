"""
LLM integration module.

Provides unified interface for multiple LLM providers.
"""

from pycore.integrations.llm.base import (
    LLMProvider,
    LLMConfig,
    LLMResponse,
    Message,
    ToolCall,
    ToolDefinition,
)
from pycore.integrations.llm.openai_provider import OpenAIProvider
from pycore.integrations.llm.token_counter import TokenCounter, estimate_tokens

__all__ = [
    # Base
    "LLMProvider",
    "LLMConfig",
    "LLMResponse",
    "Message",
    "ToolCall",
    "ToolDefinition",
    # Providers
    "OpenAIProvider",
    # Utilities
    "TokenCounter",
    "estimate_tokens",
]


def create_provider(
    provider_type: str = "openai",
    **kwargs,
) -> LLMProvider:
    """
    Factory function to create LLM provider.

    Args:
        provider_type: One of "openai", "azure", "ollama"
        **kwargs: Provider-specific configuration

    Returns:
        Configured LLM provider

    Usage:
        provider = create_provider("openai", api_key="sk-...")
        response = await provider.chat([Message(role="user", content="Hello")])
    """
    providers = {
        "openai": OpenAIProvider,
        "azure": OpenAIProvider,  # Uses same class with different config
        "ollama": OpenAIProvider,  # Uses same class with different base_url
    }

    if provider_type not in providers:
        raise ValueError(f"Unknown provider: {provider_type}. Available: {list(providers.keys())}")

    return providers[provider_type](**kwargs)
