"""HTTP API.  Run locally:  uv run uvicorn app.main:app --reload"""
import json
import logging
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager

import openai
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.agent.service import AgentResult
from app.config import Settings, get_settings
from app.schemas import AskRequest, AskResponse

logger = logging.getLogger("larkspur.api")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())

Ask = Callable[[str], AgentResult]
Stream = Callable[[str], Iterator[dict]]
LLM_DOWN = "The AI service is unavailable. Please try again."
CRASHED = "Something went wrong while answering. Please try again."


def _everyone() -> str:
    return "everyone"  # one shared bucket: the global daily budget


def _log_answer(question: str, result: dict) -> None:
    usage = result.get("usage", {})
    logger.info("answered steps=%d tokens=%d cost=$%.4f latency=%dms stopped_early=%s q=%r",
                len(result.get("steps", [])),
                usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                usage.get("cost_usd", 0.0), result.get("latency_ms", 0),
                result.get("stopped_early", False), question[:120])


def create_app(settings: Settings | None = None, ask: Ask | None = None,
               stream: Stream | None = None) -> FastAPI:
    """ask=None builds the real agent at startup; tests pass fakes. Without a stream
    function, /ask/stream falls back to one final result from ask."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = None
        if ask is None:
            from app.wiring import build_runtime  # heavy imports only for the real app
            runtime = build_runtime(settings)
            app.state.ask, app.state.stream = runtime.ask, runtime.stream
        else:
            app.state.ask = ask
            app.state.stream = stream or (
                lambda q: iter([{"type": "result", "result": ask(q).to_dict()}]))
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

    # /ask and /ask/stream share one budget per visitor, plus one daily budget for everyone
    # (many visitors, or one visitor with many IPs, can't drain the LLM balance)
    per_visitor = limiter.shared_limit(settings.rate_limit, scope="ask")
    global_daily = limiter.shared_limit(settings.daily_question_limit, scope="daily",
                                        key_func=_everyone)

    @app.post("/ask", response_model=AskResponse)
    @per_visitor
    @global_daily
    def ask_question(request: Request, body: AskRequest) -> AskResponse:
        # a plain def runs in FastAPI's thread pool, so the blocking agent call is fine
        try:
            result = request.app.state.ask(body.question)
        except openai.APIError as e:  # DeepSeek is unreachable, rate-limited or erroring
            logger.warning("LLM error: %s", e)
            raise HTTPException(503, LLM_DOWN) from e
        _log_answer(body.question, result.to_dict())
        return AskResponse(**result.to_dict())

    @app.post("/ask/stream")
    @per_visitor
    @global_daily
    def ask_question_stream(request: Request, body: AskRequest) -> StreamingResponse:
        """Server-Sent Events: step / token / result events while the agent works."""
        events = request.app.state.stream(body.question)

        def sse() -> Iterator[str]:
            # the 200 status and headers are already sent, so failures become events
            try:
                for event in events:
                    if event["type"] == "result":
                        _log_answer(body.question, event["result"])
                    yield f"data: {json.dumps(event, default=str)}\n\n"
            except openai.APIError as e:
                logger.warning("LLM error while streaming: %s", e)
                yield f"data: {json.dumps({'type': 'error', 'message': LLM_DOWN})}\n\n"
            except Exception:  # log the details, show users a generic message
                logger.exception("Agent crashed while streaming")
                yield f"data: {json.dumps({'type': 'error', 'message': CRASHED})}\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
