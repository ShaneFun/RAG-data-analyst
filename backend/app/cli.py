"""Ask the real agent from the terminal (needs DEEPSEEK_API_KEY in backend/.env).

Usage (from backend/):  uv run python -m app.cli "Why did North sales drop in March 2025?"
"""
import json
import sys

from app.config import get_settings
from app.wiring import build_runtime


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    question = " ".join(sys.argv[1:]) or "Why did North sales drop in March 2025?"
    runtime = build_runtime(get_settings())
    try:
        result = runtime.ask(question)
    finally:
        runtime.close()
    print(f"\nQ: {question}\n")
    for i, step in enumerate(result.steps, 1):
        print(f"  step {i}: {step['tool']} -> {'ok' if step['ok'] else 'ERROR'}: {step['summary']}")
        if step["tool"] == "run_sql":
            print("          " + step["input"].get("sql", "").replace("\n", " ")[:160])
    print(f"\nA: {result.answer}\n")
    print(json.dumps({"rows": len(result.rows), "chart": result.chart_hint, **result.usage,
                      "latency_ms": result.latency_ms}, indent=2))


if __name__ == "__main__":
    main()
