import pytest


@pytest.fixture(autouse=True)
def _force_sqlite(monkeypatch):
    monkeypatch.delenv("LOVKTV_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
