from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    app_name: str = "Clinical Evidence Graph"
    environment: str = "development"
    api_bearer_token: str = "dev-local-token"

    # Database
    database_url: str = (
        "postgresql+psycopg://ceg:ceg@localhost:5433/ceg"
    )

    # Anthropic / Claude
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5"

    # ASR provider
    assemblyai_api_key: str = ""

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Mock EHR receiving endpoint
    mock_ehr_base_url: str = "http://localhost:8000/mock-ehr"


@lru_cache
def get_settings() -> Settings:
    return Settings()
