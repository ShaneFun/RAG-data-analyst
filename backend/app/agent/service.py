"""Run one question through the agent graph and package the result for the API."""
import time
from dataclasses import asdict, dataclass, field

from langchain_core.messages import AIMessage, HumanMessage

from app.charts import chart_hint

STEP_LIMIT_MESSAGE = ("I couldn't finish answering within the step limit. "
                      "Try asking a narrower question.")


@dataclass
class AgentResult:
    answer: str
    sql: list[str] = field(default_factory=list)       # every successful query, in order
    columns: list[str] = field(default_factory=list)   # result of the LAST successful query
    rows: list[list] = field(default_factory=list)
    chart_hint: dict = field(default_factory=lambda: {"type": "none", "x": None, "y": None})
    steps: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    latency_ms: int = 0
    stopped_early: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def message_text(message: AIMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content.strip()
    parts = [block.get("text", "") for block in content
             if isinstance(block, dict) and block.get("type") == "text"]
    return "\n".join(parts).strip()


def run_agent(graph, question: str, *, max_steps: int = 8, input_price_per_m: float = 0.0,
              output_price_per_m: float = 0.0) -> AgentResult:
    started = time.perf_counter()
    state = graph.invoke(
        {"messages": [HumanMessage(question)], "tool_steps": 0, "steps": [],
         "last_result": None},
        {"recursion_limit": 4 * max_steps + 10},
    )
    final = state["messages"][-1]
    stopped_early = bool(getattr(final, "tool_calls", None))
    answer = STEP_LIMIT_MESSAGE if stopped_early else message_text(final)

    input_tokens = output_tokens = 0
    for msg in state["messages"]:
        usage = getattr(msg, "usage_metadata", None) or {}
        input_tokens += usage.get("input_tokens", 0)
        output_tokens += usage.get("output_tokens", 0)
    cost = (input_tokens * input_price_per_m + output_tokens * output_price_per_m) / 1_000_000

    last = state.get("last_result") or {}
    columns, rows = last.get("columns", []), last.get("rows", [])
    return AgentResult(
        answer=answer,
        sql=[s["input"].get("sql", "") for s in state["steps"]
             if s["tool"] == "run_sql" and s["ok"]],
        columns=columns,
        rows=rows,
        chart_hint=chart_hint(columns, rows),
        steps=state["steps"],
        usage={"input_tokens": input_tokens, "output_tokens": output_tokens,
               "cost_usd": round(cost, 6)},
        latency_ms=int((time.perf_counter() - started) * 1000),
        stopped_early=stopped_early,
    )
