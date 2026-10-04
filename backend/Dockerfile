# API image. Build context = backend/ (also what Render uses).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    FASTEMBED_CACHE_PATH=/opt/models \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1) dependencies only: this layer is cached until uv.lock changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) bake the embedding model into the image so the first request isn't a 70 MB download
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

# 3) our code
COPY app ./app
RUN uv sync --frozen --no-dev

# run as a non-root user
RUN useradd --create-home appuser && chown -R appuser /opt/models
USER appuser

EXPOSE 8000
# PORT is set by Render; --proxy-headers so the rate limiter sees the real client IP
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
