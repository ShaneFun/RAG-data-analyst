"""The evaluation set itself must be valid: well-formed, unseen, and every gold query runs."""
import pytest

from app.db import make_pool
from app.sql.executor import run_select
from data.knowledge_entries import load_examples
from evals.questions import load_questions
from evals.scoring import score_item

QUESTIONS = load_questions()


def test_thirty_unique_questions_each_with_a_scoring_rule():
    assert len(QUESTIONS) == 30
    assert len({q["id"] for q in QUESTIONS}) == 30
    for q in QUESTIONS:
        assert q["tags"], q["id"]
        assert q.get("gold_sql") or q.get("keywords") or q.get("expect_refusal"), q["id"]


def test_no_question_is_a_knowledge_base_example():
    examples = {e["question"].strip().lower() for e in load_examples()}
    assert not examples & {q["question"].strip().lower() for q in QUESTIONS}


@pytest.fixture(scope="module")
def ro_pool(loaded_db):
    pool = make_pool(loaded_db["ro_url"], max_size=1)
    yield pool
    pool.close()


@pytest.mark.parametrize("item", [q for q in QUESTIONS if q.get("gold_sql")], ids=lambda q: q["id"])
def test_gold_sql_runs_as_read_only_role(ro_pool, item):
    result = run_select(ro_pool, item["gold_sql"])
    assert result.ok, result.error
    assert result.rows
    # the gold result must score as a pass against itself
    assert score_item(item, "", 1, result.rows, result.rows)["passed"]


def test_planted_trends_are_visible_in_gold_results(ro_pool):
    by_id = {q["id"]: q for q in QUESTIONS}
    north = dict(run_select(ro_pool, by_id["q20"]["gold_sql"]).rows)
    assert north["2025-03-01"] < 0.3 * north["2025-02-01"]           # T3
    suppliers = dict(run_select(ro_pool, by_id["q21"]["gold_sql"]).rows)
    assert max(suppliers, key=suppliers.get) == "Brightline Goods"   # T2
