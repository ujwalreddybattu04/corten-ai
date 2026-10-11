"""
Available LLM models registry.
"""

AVAILABLE_MODELS = {
    "gpt-4o": {"provider": "openai", "label": "GPT-4o", "is_pro": False},
    "gpt-4-turbo": {"provider": "openai", "label": "GPT-4 Turbo", "is_pro": True},
    "claude-3.5-sonnet": {"provider": "anthropic", "label": "Claude 3.5 Sonnet", "is_pro": True},
    "claude-3-opus": {"provider": "anthropic", "label": "Claude 3 Opus", "is_pro": True},
    "gemini-pro": {"provider": "google", "label": "Gemini Pro", "is_pro": True},
}

DEFAULT_MODEL = "gpt-4o"
