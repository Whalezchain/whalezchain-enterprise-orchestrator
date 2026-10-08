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


def test_settlement_bond_endpoint_returns_verified_canonical_snapshot(
    tmp_path,
    monkeypatch,
):
    from urllib.parse import quote

    from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore
    from whalezchain_orchestrator.mainnet.genesis import GenesisValidator, build_genesis
    from whalezchain_orchestrator.mainnet.genesis_economic_state import (
        initialize_genesis_economic_state,
    )

    monkeypatch.setenv(
        "WHALEZ_CHAIN_INTERNAL_TOKEN",
        "test-internal-token",
    )
    monkeypatch.setenv(
        "WHALEZCHAIN_MAINNET_STORE_PATH",
        str(tmp_path / "chain"),
    )

    account_id = "whalezchain://account/deltaalpha-settlement"
    economic_state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000.00000000",
    )
    economic_state["accounts"][account_id] = {
        "level": "L3",
        "trading_capital": "600.00000000",
        "whz_bond": "100.00000000",
        "whz_bond_locked": "25.00000000",
    }

    genesis = build_genesis(
        genesis_timestamp="2026-09-30T00:00:00Z",
        initial_state={},
        validators=(
            GenesisValidator(
                validator_id="validator-1",
                public_key="00" * 32,
            ),
        ),
        authority_config={"mode": "test"},
        economic_state=economic_state,
    )

    store = MainnetChainStore(tmp_path / "chain")
    store.initialize_genesis(genesis)

    encoded_account = quote(account_id, safe="")
    response = client.get(
        f"/mainnet/settlement/account/{encoded_account}/settlement-bond",
        params={"required_whz": "50.00000000"},
        headers={
            "X-WHALEZ-CHAIN-TOKEN": "test-internal-token",
            "X-WHALEZ-CORRELATION-ID": "corr-http-001",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "VERIFIED"
    assert body["account_id"] == account_id
    assert body["available_whz"] == "75.00000000"
    assert body["locked_whz"] == "25.00000000"
    assert body["reserved_whz"] == "25.00000000"
    assert body["required_whz"] == "50.00000000"
    assert body["chain_verification"]["verified"] is True


def test_settlement_bond_endpoint_rejects_insufficient_bond(
    tmp_path,
    monkeypatch,
):
    from urllib.parse import quote

    from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore
    from whalezchain_orchestrator.mainnet.genesis import GenesisValidator, build_genesis
    from whalezchain_orchestrator.mainnet.genesis_economic_state import (
        initialize_genesis_economic_state,
    )

    monkeypatch.setenv(
        "WHALEZ_CHAIN_INTERNAL_TOKEN",
        "test-internal-token",
    )
    monkeypatch.setenv(
        "WHALEZCHAIN_MAINNET_STORE_PATH",
        str(tmp_path / "chain"),
    )

    account_id = "whalezchain://account/deltaalpha-settlement"
    economic_state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000.00000000",
    )
    economic_state["accounts"][account_id] = {
        "level": "L3",
        "trading_capital": "600.00000000",
        "whz_bond": "100.00000000",
        "whz_bond_locked": "25.00000000",
    }

    genesis = build_genesis(
        genesis_timestamp="2026-09-30T00:00:00Z",
        initial_state={},
        validators=(
            GenesisValidator(
                validator_id="validator-1",
                public_key="00" * 32,
            ),
        ),
        authority_config={"mode": "test"},
        economic_state=economic_state,
    )
    store = MainnetChainStore(tmp_path / "chain")
    store.initialize_genesis(genesis)

    response = client.get(
        f"/mainnet/settlement/account/{quote(account_id, safe='')}/settlement-bond",
        params={"required_whz": "76.00000000"},
        headers={
            "X-WHALEZ-CHAIN-TOKEN": "test-internal-token",
            "X-WHALEZ-CORRELATION-ID": "corr-http-002",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "settlement_whz_bond_insufficient"
