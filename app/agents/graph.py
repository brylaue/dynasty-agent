from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage

from app.tools import sleeper_tools
from app.tools import web_tools
from app.services import analysis
from app.services.logging import append_agent_log
from app.services.llm_router import make_llm


class AgentState(BaseModel):
    question: str
    preferences: Dict[str, Any] | None = None
    intent: Optional[str] = None
    data: Dict[str, Any] = {}
    answer: Optional[str] = None
    sources: List[Dict[str, Any]] = []
    timings: Dict[str, float] = {}


SYSTEM_PROMPT = (
    "You are a Fantasy Football research agent for a Sleeper league. "
    "Classify questions into one of: 'league_info', 'rosters', 'matchups', 'players_search', 'trending', 'nfl_state', 'start_sit', 'trade', 'waivers'."
)

SYNTH_PROMPT = (
    "You are a Fantasy Football research agent. Use the provided context and user preferences to answer the user's question with concise, actionable advice. "
    "Emphasize league-specific factors (roster size, starting slots, scoring) and the user's team status when relevant. "
    "If appropriate, add a short bullet list of recommendations."
)


def _llm():
    return make_llm()


async def classify_intent(state: AgentState) -> AgentState:
    t0 = time.perf_counter()
    llm = _llm()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Question: {state.question}\nRespond with only the intent label."),
    ]
    result = await llm.ainvoke(messages)
    intent = (result.content or "").strip().lower()
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
        "waiver": "waivers",
        "waivers": "waivers",
    }
    for key, val in mapping.items():
        if key in intent:
            intent = val
            break
    if intent not in mapping.values():
        intent = "rosters"
    t1 = time.perf_counter()
    return AgentState(
        question=state.question,
        preferences=state.preferences,
        intent=intent,
        data={},
        sources=[],
        timings={"classify_s": t1 - t0},
    )


def _compute_league_profile(league: Dict[str, Any]) -> Dict[str, Any]:
    roster_positions = league.get("roster_positions") or []
    scoring = league.get("scoring_settings") or {}
    total_rosters = league.get("total_rosters")
    # Derive starting slots and roster size (exclude bench BN)
    starting_slots = [pos for pos in roster_positions if str(pos).upper() != "BN"]
    roster_size = len(roster_positions)
    profile = {
        "league_id": league.get("league_id"),
        "name": league.get("name"),
        "season": league.get("season"),
        "status": league.get("status"),
        "total_rosters": total_rosters,
        "roster_size": roster_size,
        "starting_slots": starting_slots,
        "scoring_settings": scoring,
    }
    # Common scoring highlights
    ppr = scoring.get("rec")
    profile["ppr"] = ppr
    td_pass = scoring.get("pass_td")
    profile["pass_td_points"] = td_pass
    return profile


def _estimate_roster_value(roster_players: List[str], player_catalog: Dict[str, Any]) -> float:
    pos_base = {"QB": 60, "RB": 70, "WR": 60, "TE": 45, "K": 10, "DEF": 15}
    total = 0.0
    for pid in roster_players or []:
        p = player_catalog.get(pid) or {}
        total += float(pos_base.get(p.get("position"), 25))
    return round(total, 1)


async def fetch_context(state: AgentState) -> AgentState:
    t0 = time.perf_counter()
    intent = state.intent or "rosters"
    sources: List[Dict[str, Any]] = []
    data: Dict[str, Any] = {"preferences": state.preferences or {}}

    # League profile and rosters
    league = await sleeper_tools.get_league_info.ainvoke({})
    sources.append({"tool": "get_league_info", "args": {}})
    league_profile = _compute_league_profile(league)
    data["league_profile"] = league_profile

    rosters = await sleeper_tools.get_rosters.ainvoke({})
    data["rosters"] = rosters
    sources.append({"tool": "get_rosters", "args": {}})

    # News/trending: perform a web search when intent indicates fresh info
    if intent in {"trending"}:
        query = f"NFL fantasy trending adds drops week {league_profile.get('season','')}"
        web = await web_tools.web_search.ainvoke({"query": query, "max_results": 5})
        data["web_results"] = web
        sources.append({"tool": "web_search", "args": {"query": query}})

    # My team snapshot
    prefs = state.preferences or {}
    owner_name = (prefs.get("roster_owner_name") or "").strip().lower()
    my_team = None
    if owner_name:
        for r in rosters:
            if str(r.get("owner") or "").strip().lower() == owner_name:
                my_team = r
                break
    if my_team:
        state_info = await sleeper_tools.get_nfl_state.ainvoke({})
        week = int(state_info.get("week") or 1)
        sources.append({"tool": "get_nfl_state", "args": {}})
        matchups = await sleeper_tools.get_matchups.ainvoke({"week": week})
        sources.append({"tool": "get_matchups", "args": {"week": week}})
        starters_ids = my_team.get("starters", []) or []
        proj_map: Dict[str, float] = {}
        for m in matchups:
            if m.get("roster_id") == my_team.get("roster_id"):
                sp = m.get("starters_points") or []
                for idx, pid in enumerate(starters_ids):
                    if idx < len(sp) and sp[idx] is not None:
                        proj_map[pid] = float(sp[idx])
                break
        data["my_team"] = {
            "owner": my_team.get("owner"),
            "roster_id": my_team.get("roster_id"),
            "wins": my_team.get("wins"),
            "losses": my_team.get("losses"),
            "starters": starters_ids,
            "projected_points": sum(proj_map.values()) if proj_map else None,
        }
        data["my_team"]["num_players"] = len(my_team.get("players") or [])

    # Intent-specific additions
    if intent == "league_info":
        pass  # league_profile already included

    elif intent == "rosters":
        pass

    elif intent == "matchups":
        state_info = await sleeper_tools.get_nfl_state.ainvoke({})
        week = int(state_info.get("week") or 1)
        matchups = await sleeper_tools.get_matchups.ainvoke({"week": week})
        previews = await analysis.build_matchup_previews(matchups)
        data.update({"nfl_state": state_info, "matchups": matchups, "matchup_previews": previews})
        sources.extend([
            {"tool": "get_nfl_state", "args": {}},
            {"tool": "get_matchups", "args": {"week": week}},
        ])

    elif intent == "players_search":
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

    elif intent == "waivers":
        trending = await sleeper_tools.get_trending_players.ainvoke({"trend_type": "add", "lookback_hours": 72, "limit": 50})
        waivers = await analysis.recommend_waivers(trending, limit=12)
        data["waiver_recommendations"] = waivers
        sources.append({"tool": "get_trending_players", "args": {"trend_type": "add", "lookback_hours": 72, "limit": 50}})

    elif intent in {"start_sit", "trade"}:
        rosters2, nfl_state = await sleeper_tools.get_rosters.ainvoke({}), await sleeper_tools.get_nfl_state.ainvoke({})
        data["rosters"] = rosters2
        data["nfl_state"] = nfl_state
        sources.extend([
            {"tool": "get_rosters", "args": {}},
            {"tool": "get_nfl_state", "args": {}},
        ])
        if intent == "start_sit":
            data["start_sit"] = await analysis.suggest_start_sit(rosters2)
        else:
            trending = await sleeper_tools.get_trending_players.ainvoke({"trend_type": "add", "lookback_hours": 48, "limit": 50})
            data["trade_suggestions"] = await analysis.suggest_trade_targets(rosters2, trending)
            sources.append({"tool": "get_trending_players", "args": {"trend_type": "add", "lookback_hours": 48, "limit": 50}})

    t1 = time.perf_counter()
    timings = dict(state.timings)
    timings["fetch_s"] = t1 - t0
    return AgentState(
        question=state.question,
        preferences=state.preferences,
        intent=intent,
        data=data,
        sources=sources,
        timings=timings,
    )


async def synthesize(state: AgentState) -> AgentState:
    t0 = time.perf_counter()
    llm = _llm()
    context_lines = [f"Intent: {state.intent}"]
    prefs = state.preferences or {}
    if prefs:
        context_lines.append(f"Preferences: {prefs}")
    for k, v in state.data.items():
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
    t1 = time.perf_counter()
    timings = dict(state.timings)
    timings["synthesize_s"] = t1 - t0

    answer = result.content or ""
    append_agent_log(
        question=state.question,
        intent=state.intent,
        preferences=state.preferences,
        sources=state.sources,
        timings=timings,
    )

    return AgentState(
        question=state.question,
        preferences=state.preferences,
        intent=state.intent,
        data=state.data,
        answer=answer,
        sources=state.sources,
        timings=timings,
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