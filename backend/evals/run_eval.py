"""Run the evaluation set against the real agent (calls DeepSeek: costs about $0.01-0.05).

    cd backend
    uv run python -m evals.run_eval              # all 30 questions
    uv run python -m evals.run_eval --only t1,t3 # a subset
    uv run python -m evals.run_eval --rescore    # re-score the saved run (free, no LLM calls)

Writes evals/results/latest.json and prints a summary table by tag.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from app.config import Settings
from app.db import make_pool
from app.sql.executor import run_select
from app.wiring import build_runtime
from evals.questions import load_questions
from evals.scoring import score_item

RESULTS_DIR = Path(__file__).with_name("results")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated question ids")
    parser.add_argument("--rescore", action="store_true",
                        help="re-score the saved results after a scoring change")
    args = parser.parse_args()
    if args.rescore:
        rescore()
        return

    items = load_questions()
    if args.only:
        wanted = set(args.only.split(","))
        items = [item for item in items if item["id"] in wanted]

    settings = Settings()
    runtime = build_runtime(settings)
    gold_pool = make_pool(settings.database_url_ro, max_size=1)
    records = []
    try:
        for item in items:
            gold_rows = gold_rows_for(gold_pool, item)
            try:
                result = runtime.ask(item["question"])
            except Exception as e:  # noqa: BLE001 - one failed call should not stop the run
                records.append({"id": item["id"], "tags": item["tags"], "passed": False,
                                "error": f"{type(e).__name__}: {e}"})
                print(f"{item['id']:4} ERROR {e}")
                continue
            score = score_item(item, result.answer, len(result.sql), result.rows, gold_rows)
            records.append({
                "id": item["id"], "tags": item["tags"], "question": item["question"],
                **score, "answer": result.answer, "sql": result.sql,
                "columns": result.columns, "rows": result.rows,
                "self_corrections": sum(1 for s in result.steps
                                        if s["tool"] == "run_sql" and not s["ok"]),
                "tool_calls": len(result.steps), "latency_ms": result.latency_ms,
                "cost_usd": result.usage.get("cost_usd", 0.0),
            })
            print(f"{item['id']:4} {'PASS' if score['passed'] else 'FAIL'} {score['checks']}")
    finally:
        gold_pool.close()
        runtime.close()

    summary = summarise(records)
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / "latest.json"
    out.write_text(json.dumps({"run_at": time.strftime("%Y-%m-%d %H:%M"), "model": settings.llm_model,
                               "summary": summary, "records": records}, indent=2),
                   encoding="utf-8")
    print_summary(summary)
    print(f"\nSaved {out}")


def gold_rows_for(pool, item: dict) -> list[list] | None:
    if not item.get("gold_sql"):
        return None
    gold = run_select(pool, item["gold_sql"])
    if not gold.ok:
        raise SystemExit(f"{item['id']}: gold SQL failed: {gold.error}")
    return gold.rows


def rescore() -> None:
    """Apply the current scoring rules to the saved answers: no new LLM calls."""
    out = RESULTS_DIR / "latest.json"
    saved = json.loads(out.read_text(encoding="utf-8"))
    items = {item["id"]: item for item in load_questions()}
    pool = make_pool(Settings().database_url_ro, max_size=1)
    try:
        for r in saved["records"]:
            if "error" in r:
                continue
            item = items[r["id"]]
            score = score_item(item, r["answer"], len(r["sql"]), r["rows"],
                               gold_rows_for(pool, item))
            if score["passed"] != r["passed"]:
                print(f"{r['id']:4} {'FAIL -> PASS' if score['passed'] else 'PASS -> FAIL'}")
            r.update(score)
    finally:
        pool.close()
    saved["summary"] = summarise(saved["records"])
    out.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    print_summary(saved["summary"])


def summarise(records: list[dict]) -> dict:
    by_tag: dict[str, list[bool]] = defaultdict(list)
    for r in records:
        for tag in r["tags"]:
            by_tag[tag].append(r["passed"])
    ok = [r for r in records if "error" not in r]
    latencies = sorted(r["latency_ms"] for r in ok)
    return {
        "total": len(records),
        "passed": sum(r["passed"] for r in records),
        "by_tag": {tag: {"passed": sum(v), "total": len(v)} for tag, v in sorted(by_tag.items())},
        "questions_with_self_correction": sum(1 for r in ok if r["self_corrections"]),
        "median_latency_ms": latencies[len(latencies) // 2] if latencies else 0,
        "total_cost_usd": round(sum(r["cost_usd"] for r in ok), 4),
    }


def print_summary(summary: dict) -> None:
    print(f"\nPassed {summary['passed']}/{summary['total']}")
    for tag, s in summary["by_tag"].items():
        print(f"  {tag:8} {s['passed']}/{s['total']}")
    print(f"Self-corrected on {summary['questions_with_self_correction']} questions, "
          f"median latency {summary['median_latency_ms'] / 1000:.1f}s, "
          f"cost ${summary['total_cost_usd']}")


if __name__ == "__main__":
    main()
