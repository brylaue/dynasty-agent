## Slack Archive (slarchive)

An on-premise archiver for Slack that captures future messages and files via Slack's official APIs and makes them searchable beyond Slack Free's 90-day visibility window. This app does not bypass Slack restrictions; it archives content your app can access from the moment it is installed and, where permitted, backfills up to Slack's available history.

### Features
- Message ingestion via Slack Events (Socket Mode)
- Optional backfill (up to what the API exposes)
- SQLite storage with FTS5 full-text search
- Minimal web UI for querying by keyword, channel, user, and date range
- File metadata capture and optional file download for locally accessible archives

### Requirements
- Python 3.10+
- A Slack app with the following:
  - Socket Mode enabled
  - Scopes (adjust as needed based on data you want to archive):
    - channels:history, channels:read, channels:join
    - groups:history, groups:read
    - im:history, im:read
    - mpim:history, mpim:read
    - users:read
    - files:read
  - Event subscriptions (for events you want to capture):
    - message.channels, message.groups, message.im, message.mpim
    - file_shared, file_change
  - App-level token (for Socket Mode): starts with `xapp-`
  - Bot token: starts with `xoxb-`

Note: Private channels and DMs require the app to be invited. The app can only access content it's permitted to access under Slack's terms and your workspace configuration.

### Setup
1. Copy `.env.example` to `.env` and set values:
   - SLACK_BOT_TOKEN
   - SLACK_APP_TOKEN
   - DATA_DIR (optional; defaults to `./data`)

2. Install dependencies:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

3. Initialize the database (auto-runs on first start). Start the web server (search UI) and Slack listener:
```bash
uvicorn slarchive.main:app --host 0.0.0.0 --port 8000 --reload
```

The Slack Socket Mode worker will start in the background within the same process.

4. (Optional) Run an initial backfill for recent history your token can access:
```bash
python -m slarchive.backfill --types public,private,im,mpim --days 90
```

### Usage
- Open the UI at `http://localhost:8000` to search.
- Query with keywords, filter by channel, user, or date range.

### Data storage
- SQLite database at `<DATA_DIR>/slarchive.db`
- Files (if downloaded) at `<DATA_DIR>/files/<file_id>/<filename>`

### Notes
- This tool does not retrieve content hidden by Slack Free limitations retroactively. It archives new content going forward and any history the API returns for your workspace and scopes.
- Ensure compliance with your organization's policies and Slack's terms.

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