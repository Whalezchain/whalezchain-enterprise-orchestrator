from fastapi.testclient import TestClient

from whalezchain_orchestrator.main import app
from whalezchain_orchestrator.execution_registry import execution_registry


client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_canonical_execution_registration():
    assert "transfer" in execution_registry.list_actions()
