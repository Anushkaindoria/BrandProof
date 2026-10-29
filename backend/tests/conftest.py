import pytest
from app.config import settings


@pytest.fixture(autouse=True)
def rules_only_mode(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "rules-only")
    monkeypatch.setattr(settings, "llm_api_key", "")
