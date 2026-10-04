"""The chat model: DeepSeek through LangChain."""
from langchain_deepseek import ChatDeepSeek

from app.config import Settings


def make_llm(settings: Settings) -> ChatDeepSeek:
    if not settings.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set (put it in backend/.env).")
    return ChatDeepSeek(
        model=settings.llm_model,
        api_key=settings.deepseek_api_key,
        temperature=0,                     # deterministic SQL
        max_tokens=2048,
        request_timeout=settings.llm_timeout_s,
        max_retries=1,                     # one retry on network/5xx errors
    )
