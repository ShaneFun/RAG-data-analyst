from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, read from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # admin connection: only for the setup scripts (data.setup_db); the API never uses it
    database_url_admin: str = "postgresql://postgres:postgres@localhost:5432/larkspur"
    # read-only connection: the only credential the running API needs
    database_url_ro: str = "postgresql://analyst_ro:analyst_ro@localhost:5432/larkspur"
    analyst_ro_password: str = "analyst_ro"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    sql_timeout: str = "5s"
    max_rows: int = 200

    # LLM (DeepSeek, via LangChain's ChatDeepSeek)
    deepseek_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout_s: float = 60.0
    # USD per 1M tokens, used only to estimate cost per question (check DeepSeek's pricing page)
    llm_input_price_per_m: float = 0.28
    llm_output_price_per_m: float = 0.42

    # Agent + API
    max_agent_steps: int = 8
    rate_limit: str = "10/hour"
    daily_question_limit: str = "200/day"   # all visitors together: caps LLM spend
    allowed_origins: str = "http://localhost:3000"


def get_settings() -> Settings:
    return Settings()
