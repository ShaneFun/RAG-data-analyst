"""Build the real agent from settings: pools, embedder, LLM, tools and graph."""
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from psycopg_pool import ConnectionPool

from app.agent.graph import build_graph
from app.agent.llm import make_llm
from app.agent.prompts import build_system_prompt
from app.agent.service import AgentResult, run_agent, stream_agent
from app.agent.tools import ToolContext, make_tools
from app.config import Settings
from app.db import make_pool
from app.knowledge.embed import Embedder


@dataclass
class AgentRuntime:
    ask: Callable[[str], AgentResult]
    stream: Callable[[str], Iterator[dict]]
    pools: list[ConnectionPool]

    def close(self) -> None:
        for pool in self.pools:
            pool.close()


def build_runtime(settings: Settings) -> AgentRuntime:
    admin_pool = make_pool(settings.database_url_admin, max_size=3)
    ro_pool = make_pool(settings.database_url_ro, max_size=5)
    tools = make_tools(ToolContext(admin_pool, ro_pool, Embedder(settings.embedding_model),
                                   settings.max_rows, settings.sql_timeout))
    llm = make_llm(settings)

    options = {"max_steps": settings.max_agent_steps,
               "input_price_per_m": settings.llm_input_price_per_m,
               "output_price_per_m": settings.llm_output_price_per_m}

    def graph():
        # built per question so the prompt always has today's date
        return build_graph(llm, tools, build_system_prompt(), settings.max_agent_steps)

    def ask(question: str) -> AgentResult:
        return run_agent(graph(), question, **options)

    def stream(question: str) -> Iterator[dict]:
        return stream_agent(graph(), question, **options)

    return AgentRuntime(ask=ask, stream=stream, pools=[admin_pool, ro_pool])
