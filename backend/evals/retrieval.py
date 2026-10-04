"""Retrieval evaluation: compare vector, keyword (BM25) and hybrid search. Free: no LLM calls.

    cd backend
    uv run python -m evals.retrieval

Metrics per mode (k = 5):
- recall@5: share of queries with at least one relevant entry in the top 5 (what the LLM sees)
- hit@1:    share of queries whose first result is relevant
- MRR:      mean of 1 / rank of the first relevant result (0 if none in the top 5)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg
import yaml

from app.config import Settings
from app.knowledge.embed import Embedder
from app.knowledge.search import search_knowledge

QUESTIONS_PATH = Path(__file__).with_name("retrieval_questions.yaml")
RESULTS_PATH = Path(__file__).with_name("results") / "retrieval.json"
MODES = ("vector", "keyword", "hybrid")


def load_retrieval_questions(path: Path = QUESTIONS_PATH) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def first_relevant_rank(titles: list[str], relevant: list[str]) -> int | None:
    return next((rank for rank, title in enumerate(titles, 1) if title in relevant), None)


def evaluate(conn, embedder: Embedder, items: list[dict], mode: str, k: int = 5) -> dict:
    ranks = []
    for item in items:
        titles = [h.title for h in search_knowledge(conn, embedder, item["query"], k=k, mode=mode)]
        ranks.append(first_relevant_rank(titles, item["relevant"]))
    n = len(items)
    return {
        "recall@5": round(sum(r is not None for r in ranks) / n, 3),
        "hit@1": round(sum(r == 1 for r in ranks) / n, 3),
        "mrr": round(sum(1 / r for r in ranks if r) / n, 3),
        "misses": [item["query"] for item, r in zip(items, ranks, strict=True) if r is None],
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    items = load_retrieval_questions()
    embedder = Embedder()
    with psycopg.connect(Settings().database_url_admin) as conn:
        results = {mode: evaluate(conn, embedder, items, mode) for mode in MODES}
    print(f"{len(items)} queries   recall@5   hit@1    MRR")
    for mode, r in results.items():
        print(f"  {mode:8}   {r['recall@5']:8.0%}   {r['hit@1']:5.0%}   {r['mrr']:.3f}")
    for mode, r in results.items():
        for query in r["misses"]:
            print(f"  missed by {mode}: {query}")
    RESULTS_PATH.parent.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
