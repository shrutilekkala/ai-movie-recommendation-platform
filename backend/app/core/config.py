from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NEXUS API"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://nexus:nexus_dev_password@localhost:5432/nexus"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:3000"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic: str = "nexus.interactions.v1"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "nexus_movies"
    embedding_model: str = "BAAI/bge-small-en"

    # TMDB is optional in local development. Create an account/token only when you want
    # Telugu catalog enrichment. Never commit the token to git.
    tmdb_bearer_token: str = ""
    tmdb_telugu_pages: int = 15
    tmdb_image_base_url: str = "https://image.tmdb.org/t/p/w500"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
