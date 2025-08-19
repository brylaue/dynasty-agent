from __future__ import annotations

import os
from typing import Any, Dict, List

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from app.tools import sleeper_tools


class AgentState(BaseModel):
    question: str
    answer: str | None = None
    sources: List[Dict[str, Any]] = []


SYSTEM_PROMPT = (
    "You are a Fantasy Football research agent specialized for a specific Sleeper league. "
    "Use the provided tools to fetch league, roster, matchup, and player data. "
    "Return a concise, actionable answer for a fantasy manager. "
    "When you use concrete data, include a brief 'Sources' section summarizing ids/names/weeks."
)


def _llm() -> ChatOpenAI:
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return ChatOpenAI(model=model, temperature=0.2)


async def plan_and_answer(state: AgentState) -> AgentState:
    llm = _llm().bind_tools(
        [
            sleeper_tools.get_league_info,
            sleeper_tools.get_rosters,
            sleeper_tools.get_matchups,
            sleeper_tools.search_players,
            sleeper_tools.get_nfl_state,
            sleeper_tools.get_trending_players,
        ]
    )

    messages: List[Any] = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=state.question),
    ]

    collected_sources: List[Dict[str, Any]] = []

    # Up to 4 tool-use iterations
    for _ in range(4):
        ai: AIMessage = await llm.ainvoke(messages)
        messages.append(ai)
        tool_calls = getattr(ai, "tool_calls", None) or ai.additional_kwargs.get("tool_calls", [])
        if not tool_calls:
            answer_text = ai.content or ""
            return AgentState(question=state.question, answer=answer_text, sources=collected_sources)

        for call in tool_calls:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            args = call.get("args", {}) if isinstance(call, dict) else getattr(call, "args", {})
            call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)

            tool_map = {
                "get_league_info": sleeper_tools.get_league_info,
                "get_rosters": sleeper_tools.get_rosters,
                "get_matchups": sleeper_tools.get_matchups,
                "search_players": sleeper_tools.search_players,
                "get_nfl_state": sleeper_tools.get_nfl_state,
                "get_trending_players": sleeper_tools.get_trending_players,
            }
            tool = tool_map.get(name)
            if tool is None:
                messages.append(ToolMessage(content=f"Unknown tool: {name}", tool_call_id=call_id or name or ""))
                continue
            try:
                result = await tool.ainvoke(args or {})
                # Add compact source line
                collected_sources.append({"tool": name, "args": args})
                messages.append(ToolMessage(content=str(result)[:6000], tool_call_id=call_id or name or ""))
            except Exception as exc:  # pragma: no cover
                messages.append(ToolMessage(content=f"Tool error: {exc}", tool_call_id=call_id or name or ""))

    final_ai: AIMessage = await llm.ainvoke(messages)
    return AgentState(question=state.question, answer=final_ai.content or "", sources=collected_sources)


def create_research_graph(sleeper_client) -> Any:
    sleeper_tools.set_sleeper_client(sleeper_client)

    graph = StateGraph(AgentState)
    graph.add_node("answer", plan_and_answer)
    graph.set_entry_point("answer")
    graph.add_edge("answer", END)
    return graph.compile()