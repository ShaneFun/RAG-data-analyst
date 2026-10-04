import json

import pytest
from langchain_core.messages import ToolMessage

from app.agent.prompts import build_system_prompt
from app.agent.tools import LLM_ROW_LIMIT, ToolContext, make_tools
from app.db import make_pool


@pytest.fixture(scope="module")
def tools(knowledge_db, embedder):
    admin = make_pool(knowledge_db["admin_url"], max_size=2)
    ro = make_pool(knowledge_db["ro_url"], max_size=2)
    yield {t.name: t for t in make_tools(ToolContext(admin, ro, embedder))}
    admin.close()
    ro.close()


def _call(tool, **args) -> ToolMessage:
    return tool.invoke({"name": tool.name, "args": args, "id": "call-1", "type": "tool_call"})


def test_tool_names_and_descriptions(tools):
    assert set(tools) == {"search_knowledge", "run_sql"}
    assert "read-only" in tools["run_sql"].description


def test_search_knowledge_returns_text_and_titles(tools):
    msg = _call(tools["search_knowledge"], query="average order value")
    assert isinstance(msg, ToolMessage) and msg.tool_call_id == "call-1"
    assert "Average order value (AOV)" in msg.content
    assert msg.artifact[0]["title"] == "Average order value (AOV)"


def test_run_sql_success(tools):
    msg = _call(tools["run_sql"], sql="SELECT region, COUNT(*) AS n FROM orders GROUP BY region")
    assert json.loads(msg.content)["ok"] is True
    assert msg.artifact["ok"] and msg.artifact["row_count"] == 4
    assert msg.artifact["columns"] == ["region", "n"]


def test_run_sql_rejection_is_text_not_crash(tools):
    msg = _call(tools["run_sql"], sql="DELETE FROM orders")
    data = json.loads(msg.content)
    assert data["ok"] is False and data["error"].startswith("Rejected:")


def test_run_sql_trims_rows_for_llm_but_not_artifact(tools):
    msg = _call(tools["run_sql"], sql="SELECT id FROM orders ORDER BY id")
    data = json.loads(msg.content)
    assert len(data["rows"]) == LLM_ROW_LIMIT and "Showing the first" in data["note"]
    assert msg.artifact["row_count"] == 200


def test_system_prompt_mentions_tools_tables_and_date():
    from datetime import date
    prompt = build_system_prompt(date(2026, 1, 15))
    assert "2026-01-15" in prompt
    for word in ("search_knowledge", "run_sql", "customers_safe", "decline"):
        assert word in prompt
