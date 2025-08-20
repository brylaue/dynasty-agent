import os
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()


def get_data_dir() -> Path:
    data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "files").mkdir(parents=True, exist_ok=True)
    return data_dir


DATA_DIR = get_data_dir()
DB_PATH = DATA_DIR / "slarchive.db"
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

if not SLACK_BOT_TOKEN:
    print("Warning: SLACK_BOT_TOKEN not set. Set in .env")
if not SLACK_APP_TOKEN:
    print("Warning: SLACK_APP_TOKEN not set. Set in .env")
