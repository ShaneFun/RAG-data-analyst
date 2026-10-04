"""Run one question through the agent graph and package the result for the API."""
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

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


def _initial_state(question: str) -> dict:
    return {"messages": [HumanMessage(question)], "tool_steps": 0, "steps": [],
            "last_result": None}


def _config(max_steps: int) -> dict:
    return {"recursion_limit": 4 * max_steps + 10}


def _result(state: dict, started: float, max_steps: int, input_price_per_m: float,
            output_price_per_m: float) -> AgentResult:
    final = state["messages"][-1]
    stopped_early = state["tool_steps"] >= max_steps     # answer was forced at the tool limit
    text = "" if getattr(final, "tool_calls", None) else message_text(final)
    answer = text or STEP_LIMIT_MESSAGE

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


def run_agent(graph, question: str, *, max_steps: int = 8, input_price_per_m: float = 0.0,
              output_price_per_m: float = 0.0) -> AgentResult:
    started = time.perf_counter()
    state = graph.invoke(_initial_state(question), _config(max_steps))
    return _result(state, started, max_steps, input_price_per_m, output_price_per_m)


def stream_agent(graph, question: str, *, max_steps: int = 8, input_price_per_m: float = 0.0,
                 output_price_per_m: float = 0.0) -> Iterator[dict]:
    """Same as run_agent, but yields events while the agent works:

    {"type": "step", "step": {...}}     after each tool call
    {"type": "token", "text": "..."}    pieces of text as the LLM writes them
    {"type": "result", "result": {...}} once, at the end (same shape as /ask)

    Text written before a tool call is thinking-out-loud, not the answer, so a client should
    clear its draft answer whenever a step arrives.
    """
    started = time.perf_counter()
    state = None
    for mode, chunk in graph.stream(_initial_state(question), _config(max_steps),
                                    stream_mode=["updates", "messages", "values"]):
        if mode == "values":
            state = chunk                                 # full state after each node
        elif mode == "updates":
            for step in (chunk.get("tools") or {}).get("steps", []):
                yield {"type": "step", "step": step}
        elif mode == "messages":
            message, meta = chunk
            if (meta.get("langgraph_node") == "agent" and isinstance(message, AIMessageChunk)
                    and isinstance(message.content, str) and message.content):
                yield {"type": "token", "text": message.content}
    result = _result(state, started, max_steps, input_price_per_m, output_price_per_m)
    yield {"type": "result", "result": result.to_dict()}
