from __future__ import annotations

import os
from typing import Any

from langchain_openai import ChatOpenAI
try:
	from langchain_groq import ChatGroq
except Exception:
	ChatGroq = None  # type: ignore


def make_llm() -> Any:
	provider = os.getenv("LLM_PROVIDER", "openai").lower()
	model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
	if provider == "groq" and ChatGroq is not None:
		groq_model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
		return ChatGroq(model=groq_model, temperature=0.2)
	# default
	return ChatOpenAI(model=model, temperature=0.2)