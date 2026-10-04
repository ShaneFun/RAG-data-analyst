from langchain_core.messages import SystemMessage, ToolMessage

from app.agent.graph import build_graph
from app.agent.service import STEP_LIMIT_MESSAGE, message_text, run_agent
from tests.fakes import GOOD_RESULT, GOOD_SQL, ScriptedLLM, ai_answer, ai_call, make_fake_tools

PROMPT = "You are a test analyst."


def _graph(responses, max_steps=8):
    llm = ScriptedLLM(responses)
    return build_graph(llm, make_fake_tools({GOOD_SQL: GOOD_RESULT}), PROMPT, max_steps), llm


def test_search_then_sql_then_answer():
    graph, llm = _graph([
        ai_call("search_knowledge", {"query": "revenue"}, "c1"),
        ai_call("run_sql", {"sql": GOOD_SQL}, "c2"),
        ai_answer("North made 10.5 and South 20.0."),
    ])
    result = run_agent(graph, "Revenue by region?", input_price_per_m=1.0, output_price_per_m=2.0)
    assert result.answer == "North made 10.5 and South 20.0."
    assert result.sql == [GOOD_SQL]
    assert result.columns == ["region", "revenue"] and result.rows == GOOD_RESULT["rows"]
    assert result.chart_hint == {"type": "bar", "x": "region", "y": "revenue"}
    assert [s["tool"] for s in result.steps] == ["search_knowledge", "run_sql"]
    assert result.steps[0]["summary"] == "Gross revenue"
    assert result.steps[1] == {"tool": "run_sql", "input": {"sql": GOOD_SQL}, "ok": True,
                               "summary": "2 rows"}
    assert result.usage == {"input_tokens": 400, "output_tokens": 80,
                            "cost_usd": round((400 * 1.0 + 80 * 2.0) / 1e6, 6)}
    assert result.stopped_early is False
    # the system prompt is always sent first, and the model sees the tool results
    assert isinstance(llm.calls[0][0], SystemMessage) and llm.calls[0][0].content == PROMPT
    assert isinstance(llm.calls[2][-1], ToolMessage)


def test_sql_error_is_sent_back_and_the_agent_self_corrects():
    graph, llm = _graph([
        ai_call("run_sql", {"sql": "SELECT broken"}, "c1"),
        ai_call("run_sql", {"sql": GOOD_SQL}, "c2"),
        ai_answer("Fixed it."),
    ])
    result = run_agent(graph, "Revenue by region?")
    assert [s["ok"] for s in result.steps] == [False, True]
    assert "bad query" in result.steps[0]["summary"]
    assert "Database error" in llm.calls[1][-1].content   # the error went back to the model
    assert result.sql == [GOOD_SQL] and result.answer == "Fixed it."


def test_stops_at_max_steps():
    looping = [ai_call("run_sql", {"sql": "SELECT broken"}, f"c{i}") for i in range(10)]
    graph, llm = _graph(looping, max_steps=3)
    result = run_agent(graph, "Loop forever", max_steps=3)
    assert result.stopped_early is True
    assert result.answer == STEP_LIMIT_MESSAGE
    assert len(result.steps) == 3 and len(llm.calls) == 4


def test_refusal_needs_no_tools():
    graph, _ = _graph([ai_answer("Sorry, I can't delete data.")])
    result = run_agent(graph, "Delete all orders")
    assert result.answer == "Sorry, I can't delete data."
    assert result.steps == [] and result.sql == [] and result.rows == []
    assert result.chart_hint["type"] == "none"


def test_unknown_and_crashing_tools_become_error_messages():
    graph, _llm = _graph([
        ai_call("does_not_exist", {}, "c1"),
        ai_call("explode", {"x": "1"}, "c2"),
        ai_answer("Done."),
    ])
    result = run_agent(graph, "Break things")
    assert [s["ok"] for s in result.steps] == [False, False]
    assert "Unknown tool" in result.steps[0]["summary"]
    assert "boom" in result.steps[1]["summary"]
    assert result.answer == "Done."


def test_message_text_handles_block_content():
    from langchain_core.messages import AIMessage
    msg = AIMessage(content=[{"type": "text", "text": "Hello"}, {"type": "text", "text": "World"}])
    assert message_text(msg) == "Hello\nWorld"
