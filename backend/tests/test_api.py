import json

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from app.agent.service import AgentResult
from app.config import Settings
from app.main import create_app


def fake_ask(question: str) -> AgentResult:
    return AgentResult(
        answer=f"Answer to: {question}",
        sql=["SELECT region, COUNT(*) AS n FROM orders GROUP BY region LIMIT 200"],
        columns=["region", "n"], rows=[["North", 2500], ["South", 2400]],
        chart_hint={"type": "bar", "x": "region", "y": "n"},
        steps=[{"tool": "run_sql", "input": {"sql": "SELECT ..."}, "ok": True,
                "summary": "2 rows"}],
        usage={"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.0},
        latency_ms=12,
    )


def make_client(ask=fake_ask, stream=None, **overrides) -> TestClient:
    settings = Settings(_env_file=None, **overrides)
    return TestClient(create_app(settings=settings, ask=ask, stream=stream))


@pytest.fixture
def client():
    with make_client() as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ask_returns_full_payload(client):
    data = client.post("/ask", json={"question": "  Orders by region?  "}).json()
    assert data["answer"] == "Answer to: Orders by region?"      # whitespace stripped
    assert data["rows"] == [["North", 2500], ["South", 2400]]
    assert data["chart_hint"] == {"type": "bar", "x": "region", "y": "n"}
    assert data["steps"][0]["summary"] == "2 rows"
    assert set(data) == {"answer", "sql", "columns", "rows", "chart_hint", "steps", "usage",
                         "latency_ms", "stopped_early"}


@pytest.mark.parametrize("body", [{}, {"question": ""}, {"question": "   "},
                                  {"question": "x" * 501}])
def test_invalid_questions_are_rejected(client, body):
    assert client.post("/ask", json=body).status_code == 422


def test_rate_limit():
    with make_client(rate_limit="2/hour") as c:
        assert c.post("/ask", json={"question": "a"}).status_code == 200
        assert c.post("/ask", json={"question": "b"}).status_code == 200
        assert c.post("/ask", json={"question": "c"}).status_code == 429


def test_llm_outage_returns_503():
    def broken(question):
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://api.deepseek.com"))

    with make_client(ask=broken) as c:
        response = c.post("/ask", json={"question": "anything"})
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"]


def test_cors_allows_only_configured_origin():
    with make_client(allowed_origins="https://demo.example.com") as c:
        ok = c.options("/ask", headers={"Origin": "https://demo.example.com",
                                        "Access-Control-Request-Method": "POST"})
        bad = c.options("/ask", headers={"Origin": "https://evil.example.com",
                                         "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "https://demo.example.com"
    assert "access-control-allow-origin" not in bad.headers


# --- Streaming endpoint (Server-Sent Events) ---

def sse_events(response) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in response.text.splitlines()
            if line.startswith("data: ")]


def test_stream_sends_steps_tokens_then_result():
    def fake_stream(question):
        yield {"type": "step", "step": {"tool": "run_sql", "input": {}, "ok": True,
                                        "summary": "2 rows"}}
        yield {"type": "token", "text": "North "}
        yield {"type": "token", "text": "leads."}
        yield {"type": "result", "result": fake_ask(question).to_dict()}

    with make_client(stream=fake_stream) as c:
        response = c.post("/ask/stream", json={"question": "Orders by region?"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = sse_events(response)
    assert [e["type"] for e in events] == ["step", "token", "token", "result"]
    assert events[-1]["result"]["answer"] == "Answer to: Orders by region?"


def test_stream_without_a_stream_function_falls_back_to_one_result(client):
    events = sse_events(client.post("/ask/stream", json={"question": "hi"}))
    assert [e["type"] for e in events] == ["result"]


def test_stream_reports_llm_outage_as_an_error_event():
    def broken_stream(question):
        yield {"type": "step", "step": {"tool": "search_knowledge", "input": {}, "ok": True,
                                        "summary": "x"}}
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://api.deepseek.com"))

    with make_client(stream=broken_stream) as c:
        events = sse_events(c.post("/ask/stream", json={"question": "anything"}))
    assert [e["type"] for e in events] == ["step", "error"]
    assert "unavailable" in events[-1]["message"]


def test_stream_validates_input_and_shares_the_rate_limit_with_ask():
    with make_client(rate_limit="2/hour") as c:
        assert c.post("/ask/stream", json={"question": " "}).status_code == 422
        assert c.post("/ask", json={"question": "a"}).status_code == 200
        assert c.post("/ask/stream", json={"question": "b"}).status_code == 200
        assert c.post("/ask/stream", json={"question": "c"}).status_code == 429
        assert c.post("/ask", json={"question": "d"}).status_code == 429
