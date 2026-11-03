import os

# Tests must never touch the developer's real demo database. This runs before any
# `app` module is imported, so settings and the SQLAlchemy engine pick it up.
os.environ["DATABASE_URL"] = "sqlite:///./test_brandproof.db"

import pytest  # noqa: E402

from app.config import settings  # noqa: E402


@pytest.fixture(autouse=True)
def rules_only_mode(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "rules-only")
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_retry_base_delay", 0)  # keep retry tests instant
