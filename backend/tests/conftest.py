from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit


def _env_file_database_url() -> str:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == "DATABASE_URL":
            return value.strip().strip('"').strip("'")
    return ""


def _database_name(url: str) -> str:
    try:
        return (urlsplit(url).path or "").lstrip("/")
    except ValueError:
        return ""


test_database_url = os.environ.get("TEST_DATABASE_URL", "").strip()
if test_database_url:
    os.environ["DATABASE_URL"] = test_database_url

active_database_url = os.environ.get("DATABASE_URL", "").strip() or _env_file_database_url()
active_database_name = _database_name(active_database_url).lower()

if not test_database_url and "test" not in active_database_name:
    raise RuntimeError(
        "Refusing to run backend tests without a throwaway database. "
        "Set TEST_DATABASE_URL, or point DATABASE_URL at a database whose name contains 'test'."
    )
