from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from whalezchain_orchestrator.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WHALEZ_CHAIN_INTERNAL_TOKEN", "test-chain-token")
    return TestClient(app)


def test_prepare_rejects_missing_chain_token(client: TestClient):
    response = client.post("/mainnet/settlement/prepare", json={})
    assert response.status_code == 401


def test_finalize_rejects_missing_chain_token(client: TestClient):
    response = client.post("/mainnet/settlement/finalize", json={})
    assert response.status_code == 401
