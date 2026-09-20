from dataclasses import replace

from whalezchain_orchestrator.mainnet.authentication import (
    AUTHORIZATION_SCHEME,
    generate_keypair,
    sign_transaction,
)
from whalezchain_orchestrator.mainnet.transaction import MainnetTransaction
from whalezchain_orchestrator.services.mainnet_candidate_service import (
    MAINNET_CHAIN_ID,
    MainnetCandidateService,
)


def _signed_transfer():
    private_key, public_key = generate_keypair()
    public_key_hex = public_key.public_bytes_raw().hex()

    tx = MainnetTransaction(
        chain_id=MAINNET_CHAIN_ID,
        tx_id="tx-phase24a-001",
        sender="whalezchain://account/" + __import__("hashlib").sha256(
            public_key.public_bytes_raw()
        ).hexdigest(),
        recipient="whalezchain://account/recipient-phase24a",
        asset_symbol="PTN",
        amount="2",
        nonce=0,
        transaction_type="transfer",
        authorization={
            "scheme": AUTHORIZATION_SCHEME,
            "public_key": public_key_hex,
            "signature": "",
        },
        ordering_key="00000000000000000001",
    )

    authorization = sign_transaction(tx, private_key)
    return replace(tx, authorization=authorization)


def _initial_state(tx):
    return {
        tx.sender: {
            "WHZ": "0.00000000",
            "PTN": "10.00000000",
            "PRN": "0.00000000",
        }
    }


def test_builds_pending_mainnet_candidate():
    tx = _signed_transfer()
    service = MainnetCandidateService()

    result = service.execute_transfer_candidate(
        transaction=tx,
        initial_state=_initial_state(tx),
        height=0,
        previous_block_hash="",
        timestamp="2026-09-20T06:00:00+00:00",
    )

    assert result["status"] == "EXECUTED_CANDIDATE"
    assert result["finalized"] is False

    assert result["receipt"]["status"] == "EXECUTED_CANDIDATE"
    assert result["receipt"]["finalized"] is False
    assert result["receipt"]["state_transition_status"] == "APPLIED"

    assert result["block"].consensus_evidence == {
        "status": "pending",
        "finalized": False,
    }

    assert result["transition"]["transaction_count"] == 1
    assert result["transition"]["state_root"]
    assert result["receipt"]["tx_hash"] == tx.tx_hash
    assert result["receipt"]["block_hash"] == result["block"].block_hash


def test_candidate_transition_changes_ptn_balance():
    tx = _signed_transfer()
    service = MainnetCandidateService()

    result = service.execute_transfer_candidate(
        transaction=tx,
        initial_state=_initial_state(tx),
        timestamp="2026-09-20T06:00:00+00:00",
    )

    state = result["transition"]["state"]

    assert state[tx.sender]["PTN"] == "8.00000000"
    assert state[tx.recipient]["PTN"] == "2.00000000"


def test_candidate_rejects_non_transfer():
    tx = _signed_transfer()
    tx = replace(tx, transaction_type="mint_prn")

    service = MainnetCandidateService()

    try:
        service.execute_transfer_candidate(
            transaction=tx,
            initial_state=_initial_state(tx),
        )
    except ValueError as exc:
        assert "transfer only" in str(exc)
    else:
        raise AssertionError("non-transfer transaction was accepted")


def test_candidate_is_deterministic_for_fixed_inputs():
    tx = _signed_transfer()
    state = _initial_state(tx)
    service = MainnetCandidateService()

    first = service.execute_transfer_candidate(
        transaction=tx,
        initial_state=state,
        height=0,
        previous_block_hash="",
        timestamp="2026-09-20T06:00:00+00:00",
    )

    second = service.execute_transfer_candidate(
        transaction=tx,
        initial_state=state,
        height=0,
        previous_block_hash="",
        timestamp="2026-09-20T06:00:00+00:00",
    )

    assert first["receipt"] == second["receipt"]
    assert first["block"].block_hash == second["block"].block_hash
    assert first["transition"]["state_root"] == second["transition"]["state_root"]
