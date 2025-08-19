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

## Deploy

### Netlify (Frontend)
- `web/` contains the static frontend.
- `netlify.toml` proxies `/api/*` to your backend. Update `YOUR-BACKEND-HOST` to your deployed FastAPI URL.

### Fly.io (Backend)
- Install flyctl, login, and launch:
```bash
fly launch --no-deploy
fly secrets set OPENAI_API_KEY=sk-... SLEEPER_LEAGUE_ID=1180244317552857088
fly deploy
```
- Set your Netlify proxy to the Fly.io URL (e.g., `https://dynasty-agent-backend.fly.dev`).

### Render (Backend)
- Use `render.yaml` Blueprint. Set environment variables in dashboard:
  - `OPENAI_API_KEY` (secret)
  - `SLEEPER_LEAGUE_ID` (optional, defaults to provided league)
  - `OPENAI_MODEL` (optional, default `gpt-4o-mini`)

## Notes
- Uses Sleeper API for your league (ID in env) and an LLM with LangGraph for tool use.
- Tools in `app/tools/sleeper_tools.py`.
- Memory in `app/services/memory.py`.
- Logs in `data/logs.jsonl`.

## iOS App Options
- SwiftUI app calling the same FastAPI endpoints; add CORS and ship to TestFlight.
- Or build a React Native/Expo app; reuse the `/api/ask` endpoint.
- For on-device UI: create a chat screen with a text field, call POST `/api/ask`, render answer.