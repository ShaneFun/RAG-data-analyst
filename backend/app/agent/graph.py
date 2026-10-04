"""The agent as a LangGraph state graph.

START -> agent --(tool calls and steps left?)--> tools -> agent -> ... -> END
"""
import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]   # the conversation (appended)
    tool_steps: int                                       # tool calls made so far
    steps: Annotated[list[dict], operator.add]            # log of every tool call (for the UI)
    last_result: dict | None                              # last successful run_sql result


def _summarize(tool_name: str, msg: ToolMessage) -> tuple[bool, str]:
    if msg.status == "error":
        return False, str(msg.content)[:200]
    artifact = msg.artifact
    if tool_name == "run_sql" and isinstance(artifact, dict):
        if artifact.get("ok"):
            return True, f"{artifact['row_count']} rows"
        return False, str(artifact.get("error", ""))[:200]
    if tool_name == "search_knowledge" and isinstance(artifact, list):
        return True, ", ".join(hit["title"] for hit in artifact) or "no matches"
    return True, str(msg.content)[:200]


def build_graph(llm: Any, tools: list[BaseTool], system_prompt: str, max_steps: int = 8):
    """llm: any LangChain chat model that supports bind_tools()."""
    tools_by_name = {t.name: t for t in tools}
    model = llm.bind_tools(tools)

    def agent(state: AgentState) -> dict:
        response = model.invoke([SystemMessage(system_prompt), *state["messages"]])
        return {"messages": [response]}

    def run_tools(state: AgentState) -> dict:
        last = state["messages"][-1]
        messages, steps, result = [], [], state.get("last_result")
        for call in last.tool_calls:
            tool = tools_by_name.get(call["name"])
            if tool is None:
                msg = ToolMessage(content=f"Unknown tool: {call['name']}",
                                  tool_call_id=call["id"], status="error")
            else:
                try:
                    msg = tool.invoke(call)
                except Exception as e:  # noqa: BLE001 - a crashing tool must not crash the agent
                    msg = ToolMessage(content=f"Tool error: {e}", tool_call_id=call["id"],
                                      status="error")
            ok, summary = _summarize(call["name"], msg)
            if call["name"] == "run_sql" and ok:
                result = msg.artifact
            messages.append(msg)
            steps.append({"tool": call["name"], "input": call["args"], "ok": ok,
                          "summary": summary})
        return {"messages": messages, "steps": steps, "last_result": result,
                "tool_steps": state["tool_steps"] + len(last.tool_calls)}

    def route(state: AgentState) -> str:
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None) and state["tool_steps"] < max_steps:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_node("tools", run_tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()
