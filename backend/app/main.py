"""HTTP API.  Run locally:  uv run uvicorn app.main:app --reload"""
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager

import openai
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.agent.service import AgentResult
from app.config import Settings, get_settings
from app.schemas import AskRequest, AskResponse

logger = logging.getLogger("larkspur.api")

Ask = Callable[[str], AgentResult]


def create_app(settings: Settings | None = None, ask: Ask | None = None) -> FastAPI:
    """ask=None builds the real agent at startup; tests pass a fake."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = None
        if ask is None:
            from app.wiring import build_runtime  # heavy imports only for the real app
            runtime = build_runtime(settings)
            app.state.ask = runtime.ask
        else:
            app.state.ask = ask
        yield
        if runtime:
            runtime.close()

    app = FastAPI(title="Larkspur AI Data Analyst", version="0.1.0", lifespan=lifespan)

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.allowed_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/ask", response_model=AskResponse)
    @limiter.limit(settings.rate_limit)
    def ask_question(request: Request, body: AskRequest) -> AskResponse:
        # a plain def runs in FastAPI's thread pool, so the blocking agent call is fine
        try:
            result = request.app.state.ask(body.question)
        except openai.APIError as e:  # DeepSeek is unreachable, rate-limited or erroring
            logger.warning("LLM error: %s", e)
            raise HTTPException(503, "The AI service is unavailable. Please try again.") from e
        return AskResponse(**result.to_dict())

    return app


app = create_app()
