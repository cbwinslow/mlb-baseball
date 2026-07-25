import os

from dotenv import load_dotenv

load_dotenv()


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and point it at your "
            "Postgres instance (see docs/DECISIONS.md ADR-002)."
        )
    return url
