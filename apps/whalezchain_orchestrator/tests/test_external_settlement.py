from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization


from whalezchain_orchestrator.mainnet.external_settlement import (
    ExternalSettlementError,
    finalize_external_settlement,
    prepare_external_settlement,
)
from whalezchain_orchestrator.mainnet.genesis import GenesisValidator, build_genesis
from whalezchain_orchestrator.mainnet.genesis_economic_state import (
    initialize_genesis_economic_state,
)


def _genesis():
    settlement_account = account("settlement")
    return build_genesis(
        genesis_timestamp="2026-09-20T05:59:00Z",
        initial_state={},
        validators=(
            GenesisValidator(
                validator_id="validator-1",
                public_key="00" * 32,
            ),
        ),
        authority_config={"mode": "test"},
        economic_state={
            **initialize_genesis_economic_state(
                ptn_genesis_supply="1000.00000000",
            ),
            "accounts": {
                settlement_account: {
                    "level": "L3",
                    "trading_capital": "0.00000000",
                    "whz_bond": "100.00000000",
                    "whz_bond_locked": "0.00000000",
                }
            },
        },
    )


def account(label: str) -> str:
    from whalezchain_orchestrator.mainnet.authentication import derive_account_id
    return derive_account_id(private_key(label).public_key().public_bytes_raw())


def private_key(label: str):
    import hashlib
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    seed = hashlib.sha256(
        f"whalezchain-test-key:{label}".encode("utf-8")
    ).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def _settlement_key_hex() -> str:
    return private_key("settlement").private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()


def _payload():
    return {
        "approval_id": "apr-live-001",
        "correlation_id": "corr-live-001",
        "idempotency_key": "idem-live-001",
        "user_id": "user-001",
        "jurisdiction": "NGA",
        "settlement_asset": "external:NGN",
        "amount_minor": 250000,
        "currency": "NGN",
        "external_provider": "paystack",
        "external_reference": "ref-001",
        "provider_transaction_id": "txn-001",
        "provider_event_id": "evt-001",
        "provider_domain": "api.paystack.co",
    }


def test_prepare_requires_explicit_mainnet_enablement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv(
        "WHALEZCHAIN_MAINNET_STORE_PATH",
        str(tmp_path / "chain"),
    )
    monkeypatch.delenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", raising=False)

    from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore

    store = MainnetChainStore(tmp_path / "chain")
    store.initialize_genesis(_genesis())

    with pytest.raises(ExternalSettlementError, match="mainnet_not_live"):
        prepare_external_settlement(_payload())


def test_prepare_then_finalize_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv(
        "WHALEZCHAIN_MAINNET_STORE_PATH",
        str(tmp_path / "chain"),
    )
    monkeypatch.setenv(
        "WHALEZCHAIN_MAINNET_EXECUTION_ENABLED",
        "true",
    )

    from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore

    store = MainnetChainStore(tmp_path / "chain")
    store.initialize_genesis(_genesis())

    prepared = prepare_external_settlement(_payload())
    assert prepared["status"] == "FINALIZATION_AUTHORIZATION_REQUIRED"
    assert prepared["finalized"] is False

    payload = {
        **_payload(),
        "block": prepared["block"],
        "finalization_payload": prepared["finalization_payload"],
        "execution_authorization": {
            "approval_id": "apr-live-001",
            "execution_hash": "exec-hash-001",
            "target_payload_hash": prepared["finalization_payload"][
                "target_payload_hash"
            ],
        },
    }

    finalized = finalize_external_settlement(payload)

    assert finalized["status"] == "FINALIZED"
    assert finalized["finality"] == "FINALIZED"
    receipt = finalized["canonical_receipt"]
    assert receipt["canonical"] is True
    assert receipt["external_settlement"]["provider_event_id"] == "evt-001"

    replayed = finalize_external_settlement(payload)
    assert replayed["replay"] is True
    assert replayed["receipt_hash"] == receipt["receipt_hash"]

    assert store.finalized_head()["height"] == 0
    assert store.verify_chain()["verified"] is True


def test_whz_requirement_commits_native_settlement_attestation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv(
        "WHALEZCHAIN_MAINNET_STORE_PATH",
        str(tmp_path / "chain"),
    )
    monkeypatch.setenv(
        "WHALEZCHAIN_MAINNET_EXECUTION_ENABLED",
        "true",
    )
    monkeypatch.setenv(
        "WHALEZ_SETTLEMENT_SIGNER_PRIVATE_KEY_HEX",
        _settlement_key_hex(),
    )

    from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore

    store = MainnetChainStore(tmp_path / "chain")
    store.initialize_genesis(_genesis())

    payload = {
        **_payload(),
        "settlement_required_whz": "10.00000000",
    }

    prepared = prepare_external_settlement(payload)
    assert prepared["block"]["transactions"][0]["transaction_type"] == "settlement_attestation"
    assert prepared["block"]["transactions"][0]["settlement_required_whz"] == "10.00000000"

    final = finalize_external_settlement({
        **payload,
        "block": prepared["block"],
        "finalization_payload": prepared["finalization_payload"],
        "execution_authorization": {
            "approval_id": "apr-live-001",
            "execution_hash": "exec-hash-whz-001",
            "target_payload_hash": prepared["finalization_payload"]["target_payload_hash"],
        },
    })

    assert final["canonical_receipt"]["settlement_status"] == "WHZ_LOCKED"
    economic_state = store._replay_economic_state()
    locked = economic_state["accounts"][account("settlement")]["whz_bond_locked"]
    assert locked == "10.00000000"
