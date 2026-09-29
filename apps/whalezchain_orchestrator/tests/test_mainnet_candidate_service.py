from dataclasses import replace

from whalezchain_orchestrator.mainnet.authentication import (
    AUTHORIZATION_SCHEME,
    generate_keypair,
    sign_transaction,
)
from whalezchain_orchestrator.mainnet.transaction import MainnetTransaction
from whalezchain_orchestrator.mainnet.genesis_economic_state import (
    initialize_genesis_economic_state,
)
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


def _economic_state():
    return initialize_genesis_economic_state(
        ptn_genesis_supply="1000.00000000",
    )


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
        economic_state=_economic_state(),
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
        economic_state=_economic_state(),
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
        economic_state=_economic_state(),
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
        economic_state=_economic_state(),
        height=0,
        previous_block_hash="",
        timestamp="2026-09-20T06:00:00+00:00",
    )

    second = service.execute_transfer_candidate(
        transaction=tx,
        initial_state=state,
        economic_state=_economic_state(),
        height=0,
        previous_block_hash="",
        timestamp="2026-09-20T06:00:00+00:00",
    )

    assert first["receipt"] == second["receipt"]
    assert first["block"].block_hash == second["block"].block_hash
    assert first["transition"]["state_root"] == second["transition"]["state_root"]


def _bonded_transfer(required_whz="25.00000000"):
    private_key, public_key = generate_keypair()
    public_key_hex = public_key.public_bytes_raw().hex()

    tx = MainnetTransaction(
        chain_id=MAINNET_CHAIN_ID,
        tx_id="tx-phase24a-bonded-001",
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
        ordering_key="00000000000000000002",
        settlement_required_whz=required_whz,
    )

    authorization = sign_transaction(tx, private_key)
    return replace(tx, authorization=authorization)


def _bonded_economic_state(tx, bond="100.00000000"):
    state = _economic_state()
    state["accounts"][tx.sender] = {
        "level": "L0",
        "trading_capital": "900.00000000",
        "whz_bond": bond,
    }
    return state


def test_candidate_locks_signed_whz_bond():
    tx = _bonded_transfer()
    service = MainnetCandidateService()

    result = service.execute_transfer_candidate(
        transaction=tx,
        initial_state=_initial_state(tx),
        economic_state=_bonded_economic_state(tx),
        height=0,
        previous_block_hash="",
        timestamp="2026-09-20T06:00:00+00:00",
    )

    economic = result["economic_state"]["accounts"][tx.sender]

    assert economic["whz_bond"] == "100.00000000"
    assert economic["whz_bond_locked"] == "25.00000000"

    assert result["receipt"]["settlement_status"] == "BOND_LOCKED"
    assert result["receipt"]["settlement_required_whz"] == "25.00000000"
    assert result["receipt"]["economic_state_root"] == (
        result["block"].economic_state_root
    )


def test_candidate_rejects_insufficient_whz_bond():
    tx = _bonded_transfer("101.00000000")
    service = MainnetCandidateService()

    try:
        service.execute_transfer_candidate(
            transaction=tx,
            initial_state=_initial_state(tx),
            economic_state=_bonded_economic_state(tx),
            timestamp="2026-09-20T06:00:00+00:00",
        )
    except ValueError as exc:
        assert "insufficient WHZ bond capacity" in str(exc)
    else:
        raise AssertionError(
            "candidate accepted insufficient WHZ bond capacity"
        )
