# Fantasy Football Research Agent (Sleeper + LangGraph)

## Quickstart

1. Python 3.10+
2. Create `.env` from `.env.example` and set `OPENAI_API_KEY`.
3. Install deps:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

4. Run server:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

5. Open http://localhost:8000 and ask questions.

## Notes
- Uses Sleeper API for your league (ID in env) and an LLM with LangGraph for tool use.
- See `app/tools/sleeper_tools.py` for available tools.

## iOS App Options
- SwiftUI app calling the same FastAPI endpoints; add CORS and ship to TestFlight.
- Or build a React Native/Expo app; reuse the `/api/ask` endpoint.
- For on-device UI: create a chat screen with a text field, call POST `/api/ask`, render answer.