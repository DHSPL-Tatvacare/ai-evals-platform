"""Application configuration from environment variables."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All config comes from env vars or .env.backend file."""

    DATABASE_URL: str = "postgresql+asyncpg://evals_user:evals_pass@localhost:5432/ai_evals_platform"
    FILE_STORAGE_TYPE: str = "local"  # "local" or "azure_blob"
    FILE_STORAGE_PATH: str = "./backend/uploads"
    API_PORT: int = 8721
    CORS_ORIGINS: str = "http://localhost:5173"

    # Azure Blob (production only)
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_STORAGE_CONTAINER: str = "evals-files"

    # LLM providers (for Phase 3 batch evaluation jobs)
    GEMINI_API_KEY: str = ""
    GEMINI_AUTH_METHOD: str = "api_key"  # "api_key" or "service_account"
    GEMINI_SERVICE_ACCOUNT_PATH: str = ""
    GEMINI_MODEL: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_VERSION: str = "2025-03-01-preview"
    AZURE_OPENAI_MODEL: str = ""
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = ""
    DEFAULT_LLM_PROVIDER: str = "gemini"
    EVAL_TEMPERATURE: float = 0.1

    # Kaira API (for live adversarial testing)
    KAIRA_API_URL: str = ""
    KAIRA_AUTH_TOKEN: str = ""
    KAIRA_TEST_USER_ID: str = ""

    # Frontend URL (used for invite link URLs — must point to where users access the app)
    APP_BASE_URL: str = "http://localhost:5173"

    # Auth / JWT
    JWT_SECRET: str = ""  # Required — validated on startup
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Bootstrap admin (used only when no users exist in DB)
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""
    ADMIN_TENANT_NAME: str = ""
    ADMIN_TENANT_ALLOWED_DOMAINS: str = ""  # Comma-separated, e.g. "@tatvacare.in,@tatva.com"

    # Adversarial test settings
    ADVERSARIAL_MAX_TURNS: int = 10
    ADVERSARIAL_TURN_DELAY: float = 1.5
    ADVERSARIAL_CASE_DELAY: float = 3.0

    class Config:
        env_file = ".env.backend"
        env_file_encoding = "utf-8"


settings = Settings()
