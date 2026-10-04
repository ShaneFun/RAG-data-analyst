from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, read from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # admin connection: setup scripts only, never given to the AI
    database_url_admin: str = "postgresql://postgres:postgres@localhost:5432/larkspur"
    # read-only connection: used to run the AI's SQL
    database_url_ro: str = "postgresql://analyst_ro:analyst_ro@localhost:5432/larkspur"
    analyst_ro_password: str = "analyst_ro"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    sql_timeout: str = "5s"
    max_rows: int = 200


def get_settings() -> Settings:
    return Settings()