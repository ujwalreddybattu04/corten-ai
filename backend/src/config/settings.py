"""
Application settings loaded from environment variables via Pydantic Settings.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, model_validator
from typing import List, Literal
from email_validator import validate_email
from urllib.parse import urlsplit


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
    RECOVERY_EMAIL_ENABLED: bool = False
    EMAIL_FROM: str = "ujwalreddybattu@gmail.com"
    EMAIL_PUBLIC_BASE_URL: str = "https://d3a7ful0miola1.cloudfront.net"
    # During SES sandbox testing only permitted recipients are accepted.
    EMAIL_ALLOWED_RECIPIENTS: List[str] = Field(default_factory=list, repr=False)
    PASSWORD_RESET_EXPIRE_MINUTES: int = Field(default=30, ge=10, le=60)

    @field_validator("EMAIL_FROM")
    @classmethod
    def validate_sender(cls, value: str) -> str:
        return validate_email(value, check_deliverability=False).normalized

    @field_validator("EMAIL_ALLOWED_RECIPIENTS")
    @classmethod
    def validate_test_recipients(cls, values: List[str]) -> List[str]:
        return list(dict.fromkeys(validate_email(value, check_deliverability=False).normalized.lower() for value in values))

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
    # Pro and Extended thinking answers, long documents, artifacts and file creation.
    HEAVY_MODEL: str = "openai/gpt-oss-120b"
    # The only configured Groq model that accepts images.
    VISION_MODEL: str = "qwen/qwen3.8-27b"
    # Room for complete artifacts and documents; gpt-oss-120b supports far more.
    LLM_HEAVY_MAX_OUTPUT_TOKENS: int = Field(default=16384, ge=1024, le=65536)

    # --- Discover / News ---
    NEWSAPI_KEY: str = ""
    GUARDIAN_API_KEY: str = ""
    OPENFDA_API_KEY: str = ""
    PHARMA_INTELLIGENCE_ENABLED: bool = False
    PHARMA_BEDROCK_SOCKET: str = "/run/corten-bedrock/gateway.sock"
    PHARMA_BRIEF_MODEL: Literal["amazon.nova-pro-v1:0"] = "amazon.nova-pro-v1:0"
    PHARMA_QUESTION_MODEL: Literal["amazon.nova-pro-v1:0", "amazon.nova-lite-v1:0"] = "amazon.nova-pro-v1:0"
    # Planning errors cost more than the planner call: the Lite planner produced unsearchable queries such as "Mounjaro (tirzepatide)".
    PHARMA_PLANNER_MODEL: Literal["amazon.nova-pro-v1:0", "amazon.nova-lite-v1:0"] = "amazon.nova-pro-v1:0"
    OPENWEATHER_API_KEY: str = ""

    # --- Web Search ---
    MAX_SEARCH_RESULTS: int = 10
    BRAVE_SEARCH_API_KEY: str = ""
    GOOGLE_SEARCH_API_KEY: str = ""
    GOOGLE_SEARCH_CX: str = ""
    BING_SEARCH_API_KEY: str = ""
    TAVILY_API_KEY: str = ""
    SERPER_API_KEY: str = ""

    # --- Spaces ---
    # Retained volume in production (see deploy/aws/compose.yaml). Never inside the image.
    SPACE_FILES_DIR: str = "space-files"
    SPACE_MAX_FILE_BYTES: int = Field(default=25 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    SPACE_MAX_FILES: int = Field(default=100, ge=1, le=10000)
    SPACE_MAX_TOTAL_BYTES: int = Field(default=500 * 1024 * 1024, ge=1024 * 1024)
    SPACE_MAX_MEMBERS: int = Field(default=50, ge=2, le=10000)
    SPACE_MAX_OWNED: int = Field(default=100, ge=1, le=10000)
    # Spaces answer with their template's agent and tools. Off falls back to the standard answer pipeline.
    SPACE_AGENTS_ENABLED: bool = True

    # --- Chat attachments and generated files ---
    ATTACHMENT_MAX_BYTES: int = Field(default=25 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    ATTACHMENT_RETENTION_DAYS: int = Field(default=90, ge=1, le=3650)
    ATTACHMENT_MAX_PER_USER: int = Field(default=1000, ge=10)
    ATTACHMENT_MAX_TOTAL_BYTES: int = Field(default=2 * 1024 * 1024 * 1024, ge=1024 * 1024)
    MEMORY_MAX_PER_USER: int = Field(default=200, ge=10, le=5000)

    # --- Rate Limiting ---
    RATE_LIMIT_PER_MINUTE: int = 30
    RATE_LIMIT_PER_DAY: int = 300

    # --- CORS ---
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def require_production_secret(self):
        if self.APP_ENV == "production" and (len(self.JWT_SECRET_KEY) < 32 or self.JWT_SECRET_KEY == "change-me-in-production"):
            raise ValueError("Set a strong JWT_SECRET_KEY of at least 32 characters in production")
        origin = urlsplit(self.EMAIL_PUBLIC_BASE_URL.rstrip("/"))
        if origin.scheme not in ("http", "https") or not origin.hostname or origin.username or origin.password or origin.path or origin.query or origin.fragment:
            raise ValueError("EMAIL_PUBLIC_BASE_URL must be the application's origin")
        if self.APP_ENV == "production" and origin.scheme != "https":
            raise ValueError("Recovery links require HTTPS in production")
        return self

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
