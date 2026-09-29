from __future__ import annotations

import pytest

from whalezchain_orchestrator.mainnet.finalization_authorization import (
    FinalizationAuthorizationError,
    MainnetFinalizationAuthorization,
    from_execution_authorization,
)
from whalezchain_orchestrator.mainnet.transaction import sha256_hex


def make_payload(**overrides):
    payload = {
        "authorization_type": "wcz.mainnet.finalization_authorization.v1",
        "approval_id": "approval-001",
        "execution_hash": "execution-001",
        "chain_id": "whalezchain-mainnet-v1",
        "genesis_hash": "genesis-001",
        "height": 7,
        "previous_block_hash": "previous-001",
        "transaction_root": "txroot-001",
        "resulting_state_root": "state-001",
        "economic_state_root": "economic-001",
        "block_hash": "block-001",
        "authority": "WHALEZ_AI",
        "execution_mode": "mainnet_finalization",
    }

    payload.update(overrides)

    payload["target_payload_hash"] = sha256_hex(
        {
            key: value
            for key, value in payload.items()
            if key != "target_payload_hash"
        }
    )

    return payload


def make_authorization(payload=None):
    payload = payload or make_payload()

    return from_execution_authorization(
        {
            "approval_id": payload["approval_id"],
            "execution_hash": payload["execution_hash"],
            "target_payload_hash": payload["target_payload_hash"],
        },
        finalization_payload=payload,
    )


def test_exact_block_binding_succeeds():
    auth = make_authorization()

    auth.matches_block(
        chain_id="whalezchain-mainnet-v1",
        genesis_hash="genesis-001",
        height=7,
        previous_block_hash="previous-001",
        transaction_root="txroot-001",
        resulting_state_root="state-001",
        economic_state_root="economic-001",
        block_hash="block-001",
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("chain_id", "attacker-chain"),
        ("genesis_hash", "attacker-genesis"),
        ("height", 8),
        ("previous_block_hash", "attacker-previous"),
        ("transaction_root", "attacker-txroot"),
        ("resulting_state_root", "attacker-state"),
        ("economic_state_root", "attacker-economic"),
        ("block_hash", "attacker-block"),
    ],
)
def test_authorization_cannot_be_retargeted(field, value):
    auth = make_authorization()

    expected = {
        "chain_id": "whalezchain-mainnet-v1",
        "genesis_hash": "genesis-001",
        "height": 7,
        "previous_block_hash": "previous-001",
        "transaction_root": "txroot-001",
        "resulting_state_root": "state-001",
        "economic_state_root": "economic-001",
        "block_hash": "block-001",
    }

    expected[field] = value

    with pytest.raises(FinalizationAuthorizationError):
        auth.matches_block(**expected)


def test_target_payload_tampering_fails():
    payload = make_payload()
    tampered = dict(payload)
    tampered["block_hash"] = "tampered-block"

    with pytest.raises(FinalizationAuthorizationError):
        make_authorization(tampered)


def test_missing_execution_authorization_field_fails():
    payload = make_payload()

    with pytest.raises(FinalizationAuthorizationError):
        from_execution_authorization(
            {
                "approval_id": payload["approval_id"],
                "execution_hash": payload["execution_hash"],
            },
            finalization_payload=payload,
        )


def test_wrong_target_payload_hash_fails():
    payload = make_payload()

    with pytest.raises(FinalizationAuthorizationError):
        from_execution_authorization(
            {
                "approval_id": payload["approval_id"],
                "execution_hash": payload["execution_hash"],
                "target_payload_hash": "0" * 64,
            },
            finalization_payload=payload,
        )


def test_authorization_hash_changes_when_block_commitment_changes():
    payload = make_payload()
    auth = make_authorization(payload)

    altered = MainnetFinalizationAuthorization(
        **{
            **auth.__dict__,
            "block_hash": "different-block",
        }
    )

    assert altered.authorization_hash != auth.authorization_hash
