"""Settings loaded from the repo-root .env file."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"

load_dotenv(REPO_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    yahoo_client_id: str
    yahoo_client_secret: str
    yahoo_redirect_uri: str
    yahoo_league_id: str
    token_path: Path
    db_url: str


def get_settings() -> Settings:
    return Settings(
        yahoo_client_id=os.environ.get("YAHOO_CLIENT_ID", ""),
        yahoo_client_secret=os.environ.get("YAHOO_CLIENT_SECRET", ""),
        yahoo_redirect_uri=os.environ.get(
            "YAHOO_REDIRECT_URI", "https://localhost:8000/auth/yahoo/callback"
        ),
        yahoo_league_id=os.environ.get("YAHOO_LEAGUE_ID", "23772"),
        token_path=Path(os.environ.get("YAHOO_TOKEN_PATH", DATA_DIR / "yahoo_token.json")),
        db_url=os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'fantasy.db'}"),
    )
