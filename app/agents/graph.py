from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage

from app.tools import sleeper_tools
from app.services import analysis


class AgentState(BaseModel):
    question: str
    intent: Optional[str] = None
    data: Dict[str, Any] = {}
    answer: Optional[str] = None
    sources: List[Dict[str, Any]] = []


SYSTEM_PROMPT = (
    "You are a Fantasy Football research agent for a Sleeper league. "
    "Classify questions into one of: 'league_info', 'rosters', 'matchups', 'players_search', 'trending', 'nfl_state', 'start_sit', 'trade'."
)

SYNTH_PROMPT = (
    "You are a Fantasy Football research agent. Use the provided context to answer the user's question with concise, actionable advice. "
    "If appropriate, add a short bullet list of recommendations."
)


def _llm() -> ChatOpenAI:
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return ChatOpenAI(model=model, temperature=0.2)


async def classify_intent(state: AgentState) -> AgentState:
    llm = _llm()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Question: {state.question}\nRespond with only the intent label."),
    ]
    result = await llm.ainvoke(messages)
    intent = (result.content or "").strip().lower()
    # Normalize
    mapping = {
        "league": "league_info",
        "league_info": "league_info",
        "roster": "rosters",
        "rosters": "rosters",
        "matchup": "matchups",
        "matchups": "matchups",
        "player": "players_search",
        "players_search": "players_search",
        "trending": "trending",
        "state": "nfl_state",
        "nfl_state": "nfl_state",
        "start": "start_sit",
        "start_sit": "start_sit",
        "trade": "trade",
    }
    for key, val in mapping.items():
        if key in intent:
            intent = val
            break
    if intent not in mapping.values():
        intent = "rosters"
    return AgentState(question=state.question, intent=intent, data={}, sources=[])


async def fetch_context(state: AgentState) -> AgentState:
    intent = state.intent or "rosters"
    sources: List[Dict[str, Any]] = []
    data: Dict[str, Any] = {}

    if intent == "league_info":
        league = await sleeper_tools.get_league_info.ainvoke({})
        data["league"] = league
        sources.append({"tool": "get_league_info", "args": {}})

    elif intent == "rosters":
        rosters = await sleeper_tools.get_rosters.ainvoke({})
        data["rosters"] = rosters
        sources.append({"tool": "get_rosters", "args": {}})

    elif intent == "matchups":
        state_info = await sleeper_tools.get_nfl_state.ainvoke({})
        week = int(state_info.get("week") or 1)
        matchups = await sleeper_tools.get_matchups.ainvoke({"week": week})
        data.update({"nfl_state": state_info, "matchups": matchups})
        sources.extend([
            {"tool": "get_nfl_state", "args": {}},
            {"tool": "get_matchups", "args": {"week": week}},
        ])

    elif intent == "players_search":
        # Heuristic: extract name fragment from the question
        frag = state.question
        players = await sleeper_tools.search_players.ainvoke({"query": frag, "limit": 10})
        data["players"] = players
        sources.append({"tool": "search_players", "args": {"query": frag, "limit": 10}})

    elif intent == "trending":
        trending = await sleeper_tools.get_trending_players.ainvoke({"trend_type": "add", "lookback_hours": 48, "limit": 25})
        data["trending"] = trending
        sources.append({"tool": "get_trending_players", "args": {"trend_type": "add", "lookback_hours": 48, "limit": 25}})

    elif intent == "nfl_state":
        state_info = await sleeper_tools.get_nfl_state.ainvoke({})
        data["nfl_state"] = state_info
        sources.append({"tool": "get_nfl_state", "args": {}})

    elif intent in {"start_sit", "trade"}:
        rosters, nfl_state = await sleeper_tools.get_rosters.ainvoke({}), await sleeper_tools.get_nfl_state.ainvoke({})
        data["rosters"] = rosters
        data["nfl_state"] = nfl_state
        sources.extend([
            {"tool": "get_rosters", "args": {}},
            {"tool": "get_nfl_state", "args": {}},
        ])
        # Augment with simple analysis
        if intent == "start_sit":
            data["start_sit"] = await analysis.suggest_start_sit(rosters)
        else:
            trending = await sleeper_tools.get_trending_players.ainvoke({"trend_type": "add", "lookback_hours": 48, "limit": 50})
            data["trade_suggestions"] = await analysis.suggest_trade_targets(rosters, trending)
            sources.append({"tool": "get_trending_players", "args": {"trend_type": "add", "lookback_hours": 48, "limit": 50}})

    return AgentState(question=state.question, intent=intent, data=data, sources=sources)


async def synthesize(state: AgentState) -> AgentState:
    llm = _llm()
    context_lines = [f"Intent: {state.intent}"]
    for k, v in state.data.items():
        # Keep context compact
        snippet = str(v)
        if len(snippet) > 4000:
            snippet = snippet[:4000] + "..."
        context_lines.append(f"{k}: {snippet}")
    context = "\n\n".join(context_lines)

    messages = [
        SystemMessage(content=SYNTH_PROMPT),
        HumanMessage(content=f"Context:\n{context}\n\nQuestion: {state.question}"),
    ]
    result = await llm.ainvoke(messages)
    return AgentState(
        question=state.question,
        intent=state.intent,
        data=state.data,
        answer=result.content or "",
        sources=state.sources,
    )


def create_research_graph(sleeper_client) -> Any:
    sleeper_tools.set_sleeper_client(sleeper_client)

    graph = StateGraph(AgentState)
    graph.add_node("classify", classify_intent)
    graph.add_node("fetch", fetch_context)
    graph.add_node("synthesize", synthesize)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "fetch")
    graph.add_edge("fetch", "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile()