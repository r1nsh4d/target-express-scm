from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://targetexpress:targetexpress@localhost:55432/targetexpress"
    )
    secret_key: str = "dev-only-secret-change-me"
    access_token_expire_minutes: int = 720
    environment: str = "development"
    cors_origins: str = "http://localhost:5173"

    # S3-compatible object storage. Hetzner Object Storage, MinIO and AWS all
    # work; only the endpoint differs.
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "target-express"
    s3_region: str = "us-east-1"
    # Set when the bucket is fronted by a CDN or a custom domain. Left blank,
    # objects are read straight from the endpoint.
    s3_public_base_url: str | None = None

    public_base_url: str = "http://localhost:5173"

    anthropic_api_key: str | None = None
    ai_model: str = "claude-sonnet-5"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
