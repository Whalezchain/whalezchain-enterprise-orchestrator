from fastapi.testclient import TestClient

from whalezchain_orchestrator.main import app
from whalezchain_orchestrator.whalezchain_testnet_engine.runtime import engine


client = TestClient(app)


def test_invalid_transfer_returns_controlled_http_error():
    before_state = engine.state()
    before_receipt = engine.receipt()

    response = client.post(
        "/testnet/transfer",
        json={
            "from_account": "",
            "to_account": "whalezchain-testnet://validator/internal-beta",
            "asset_symbol": "PTN",
            "amount": "1.00000000",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "status": "error",
        "error": "validation_error",
        "detail": "missing source account",
    }

    after_state = engine.state()
    after_receipt = engine.receipt()

    assert after_state["journal_count"] == before_state["journal_count"]
    assert after_receipt["state_root"] == before_receipt["state_root"]


def test_health_remains_available():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_canonical_assets_are_exposed_read_only():
    response = client.get("/assets")

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "ok"
    assert set(body["assets"]) == {"WHZ", "PTN", "PRN"}
    assert body["assets"]["WHZ"]["canonical_asset_name"] == "Whalez-Mint"
    assert body["assets"]["PTN"]["canonical_asset_name"] == "Plutonium"
    assert body["assets"]["PRN"]["canonical_asset_name"] == "Plutoranium"
    assert all(
        body["assets"][symbol]["identity_status"] == "CANONICAL"
        for symbol in ("WHZ", "PTN", "PRN")
    )
