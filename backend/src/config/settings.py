"""
Application settings loaded from environment variables via Pydantic Settings.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, model_validator
from typing import List, Literal


class Settings(BaseSettings):
    # --- App ---
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    BRAND_NAME: str = "Corten"
    COMPANY_NAME: str = "Chryselys Private Limited"
    COMPANY_WEBSITE: str = "https://chryselys.com"
    BRAND_DESCRIPTION: str = "the AI assistant developed by Chryselys Private Limited"

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://corten:corten_dev@localhost:5432/corten_ai"
    DATABASE_POOL_SIZE: int = Field(default=5, ge=1, le=50)
    DATABASE_MAX_OVERFLOW: int = Field(default=10, ge=0, le=50)

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def use_async_postgres_driver(cls, value: str) -> str:
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value[len(prefix):]
        return value

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- JWT ---
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- OAuth ---
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    # --- LLM Providers ---
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_AI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GROQ_FALLBACK_API_KEYS: List[str] = Field(default_factory=list, max_length=4, repr=False)
    LLM_PROVIDER: Literal["groq", "gemini"] = "groq"
    # Fallback must be explicitly enabled; merely supplying another key does not send it data.
    LLM_FALLBACK_PROVIDER: Literal["", "groq", "gemini"] = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    LLM_MAX_OUTPUT_TOKENS: int = Field(default=2048, ge=256, le=32768)

    @field_validator("GROQ_FALLBACK_API_KEYS")
    @classmethod
    def clean_groq_fallback_keys(cls, values: List[str]) -> List[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))
    
    # Models
    DEFAULT_MODEL: str = "openai/gpt-oss-20b"
    ROUTER_MODEL: str = "openai/gpt-oss-20b"

    # --- Discover / News ---
    NEWSAPI_KEY: str = ""
    GUARDIAN_API_KEY: str = ""
    OPENFDA_API_KEY: str = ""
    OPENWEATHER_API_KEY: str = ""

    # --- Web Search ---
    MAX_SEARCH_RESULTS: int = 10
    BRAVE_SEARCH_API_KEY: str = ""
    GOOGLE_SEARCH_API_KEY: str = ""
    GOOGLE_SEARCH_CX: str = ""
    BING_SEARCH_API_KEY: str = ""
    TAVILY_API_KEY: str = ""
    SERPER_API_KEY: str = ""

    # --- Rate Limiting ---
    RATE_LIMIT_PER_MINUTE: int = 30
    RATE_LIMIT_PER_DAY: int = 300

    # --- CORS ---
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def require_production_secret(self):
        if self.APP_ENV == "production" and (len(self.JWT_SECRET_KEY) < 32 or self.JWT_SECRET_KEY == "change-me-in-production"):
            raise ValueError("Set a strong JWT_SECRET_KEY of at least 32 characters in production")
        return self

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
