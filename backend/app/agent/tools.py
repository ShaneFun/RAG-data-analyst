"""The two tools the LLM can call. Each returns (text for the LLM, artifact for the API)."""
import json
from dataclasses import dataclass

from langchain_core.tools import BaseTool, tool
from psycopg_pool import ConnectionPool

from app.knowledge.embed import Embedder
from app.knowledge.search import search_knowledge as _search
from app.sql.executor import run_select

LLM_ROW_LIMIT = 50  # rows shown to the LLM; the API still returns up to max_rows


@dataclass
class ToolContext:
    admin_pool: ConnectionPool    # knowledge search (the read-only role can't read it)
    ro_pool: ConnectionPool       # agent SQL, as analyst_ro
    embedder: Embedder
    max_rows: int = 200
    sql_timeout: str = "5s"


def make_tools(ctx: ToolContext) -> list[BaseTool]:
    @tool(response_format="content_and_artifact")
    def search_knowledge(query: str) -> tuple[str, list[dict]]:
        """Search the shop's knowledge base: table descriptions with column values, business
        definitions (revenue, refund rate, AOV...) and example SQL. Use before writing SQL."""
        with ctx.admin_pool.connection() as conn:
            hits = _search(conn, ctx.embedder, query, k=5)
        if not hits:
            return "No knowledge found for that query.", []
        text = "\n\n".join(f"[{h.kind}] {h.title}\n{h.content}" for h in hits)
        return text, [{"kind": h.kind, "title": h.title, "score": round(h.score, 3)} for h in hits]

    @tool(response_format="content_and_artifact")
    def run_sql(sql: str) -> tuple[str, dict]:
        """Run ONE read-only PostgreSQL SELECT on the shop database (max 200 rows).
        Allowed tables: customers_safe, products, orders, order_items, refunds."""
        result = run_select(ctx.ro_pool, sql, max_rows=ctx.max_rows, timeout=ctx.sql_timeout)
        payload = result.to_dict()
        for_llm = dict(payload)
        if result.row_count > LLM_ROW_LIMIT:
            for_llm["rows"] = payload["rows"][:LLM_ROW_LIMIT]
            for_llm["note"] = f"Showing the first {LLM_ROW_LIMIT} of {result.row_count} rows."
        return json.dumps(for_llm, default=str), payload

    return [search_knowledge, run_sql]
