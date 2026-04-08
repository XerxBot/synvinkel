from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://synvinkel:synvinkel_dev@localhost:5432/synvinkel"
    DATABASE_URL_SYNC: str = "postgresql://synvinkel:synvinkel_dev@localhost:5432/synvinkel"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "dev-secret-change-in-production"
    ADMIN_EMAIL: str = "xerxes@analytech.se"
    ENVIRONMENT: str = "development"

    SCRAPE_RATE_LIMIT_SECONDS: float = 1.5
    USER_AGENT: str = "Synvinkel/0.1 (+https://synvinkel.analytech.se; research bot)"
    ALLOWED_ORIGINS: str = "http://localhost:4321,http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
