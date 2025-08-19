# Fantasy Football Research Agent (Sleeper + LangGraph)

## Quickstart

1. Python 3.10+
2. Create `.env` from `.env.example` and set `OPENAI_API_KEY`.
   - `OPENAI_MODEL` defaults to `gpt-5`. You can set `gpt-4o` or `gpt-4o-mini` for lower cost.
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
- `netlify.toml` proxies `/api/*` to your backend.

### Backend
- Render or Fly.io. Set env vars:
  - `OPENAI_API_KEY`
  - `SLEEPER_LEAGUE_ID`
  - `OPENAI_MODEL` (default `gpt-5`)

## Notes
- Tools in `app/tools/sleeper_tools.py`.
- Memory in `app/services/memory.py`.
- Logs in `data/logs.jsonl`.
- Consider a hybrid model setup: use `gpt-4o-mini` for planning/tool use and `gpt-5` for final synthesis.

## iOS App Options
- SwiftUI app calling the same FastAPI endpoints; add CORS and ship to TestFlight.
- Or build a React Native/Expo app; reuse the `/api/ask` endpoint.
- For on-device UI: create a chat screen with a text field, call POST `/api/ask`, render answer.