"""Test configuration: isolated SQLite file and no network calls to Gemini."""

import os
import pathlib
import sys
import tempfile

_TMP = pathlib.Path(tempfile.mkdtemp(prefix="minerakshak-tests-"))

os.environ["DB_PATH"] = str(_TMP / "test.db")
os.environ["AGENT_LLM_MODE"] = "offline"
os.environ["SEED_DEMO"] = "1"
os.environ["DEMO_EMAIL"] = "demo@test.local"
os.environ["DEMO_PASSWORD"] = "demo1234"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client():
    """Shared API client; the lifespan hook creates the schema and demo user."""
    import main

    with TestClient(main.app) as test_client:
        yield test_client
