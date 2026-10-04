"""Request/response models for the HTTP API."""
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class ChartHint(BaseModel):
    type: Literal["line", "bar", "none"]
    x: str | None = None
    y: str | None = None


class Step(BaseModel):
    tool: str
    input: dict[str, Any]
    ok: bool
    summary: str


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class AskResponse(BaseModel):
    answer: str
    sql: list[str]
    columns: list[str]
    rows: list[list[Any]]
    chart_hint: ChartHint
    steps: list[Step]
    usage: Usage
    latency_ms: int
    stopped_early: bool
