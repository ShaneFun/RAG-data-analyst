"""Test doubles: a scripted chat model and simple tools (no API calls, no database)."""
import json

from langchain_core.messages import AIMessage
from langchain_core.tools import tool


class ScriptedLLM:
    """Returns pre-written AIMessages in order; records what it was sent."""

    def __init__(self, responses: list[AIMessage]):
        self.responses = list(responses)
        self.calls: list[list] = []

    def bind_tools(self, tools):
        self.bound_tools = [t.name for t in tools]
        return self

    def invoke(self, messages):
        self.calls.append(list(messages))
        if not self.responses:
            raise AssertionError("ScriptedLLM ran out of responses")
        return self.responses.pop(0)


def ai_call(name: str, args: dict, call_id: str, tokens: tuple[int, int] = (100, 20)) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}],
                     usage_metadata={"input_tokens": tokens[0], "output_tokens": tokens[1],
                                     "total_tokens": sum(tokens)})


def ai_answer(text: str, tokens: tuple[int, int] = (200, 40)) -> AIMessage:
    return AIMessage(content=text, usage_metadata={"input_tokens": tokens[0],
                                                   "output_tokens": tokens[1],
                                                   "total_tokens": sum(tokens)})


def make_fake_tools(sql_results: dict[str, dict]):
    """run_sql returns the dict mapped to the exact SQL text (default: an error)."""

    @tool(response_format="content_and_artifact")
    def search_knowledge(query: str) -> tuple[str, list[dict]]:
        """Fake knowledge search."""
        return f"[glossary] Gross revenue\nSUM(quantity * unit_price) for '{query}'", \
            [{"kind": "glossary", "title": "Gross revenue", "score": 0.9}]

    @tool(response_format="content_and_artifact")
    def run_sql(sql: str) -> tuple[str, dict]:
        """Fake SQL runner."""
        result = sql_results.get(sql, {"ok": False, "sql": sql, "columns": [], "rows": [],
                                       "row_count": 0, "error": "Database error: bad query"})
        return json.dumps(result), result

    @tool
    def explode(x: str) -> str:
        """Always crashes."""
        raise RuntimeError("boom")

    return [search_knowledge, run_sql, explode]


GOOD_SQL = "SELECT region, SUM(x) AS revenue FROM orders GROUP BY region"
GOOD_RESULT = {"ok": True, "sql": GOOD_SQL + " LIMIT 200", "columns": ["region", "revenue"],
               "rows": [["North", 10.5], ["South", 20.0]], "row_count": 2, "error": None}
