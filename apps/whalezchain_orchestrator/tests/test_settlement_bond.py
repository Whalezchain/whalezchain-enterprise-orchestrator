from decimal import Decimal

import pytest

from whalezchain_orchestrator.mainnet.genesis_economic_state import (
    initialize_genesis_economic_state,
    economic_state_root,
)
from whalezchain_orchestrator.mainnet.settlement_bond import (
    SettlementBondStateError,
    get_settlement_bond_state,
)


def _state() -> dict:
    state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000.00000000",
    )
    state["accounts"]["deltaalpha-settlement"] = {
        "level": "L0",
        "trading_capital": "900.00000000",
        "whz_bond": "100.00000000",
        "whz_bond_locked": "25.00000000",
    }
    return state


def _head() -> dict:
    return {
        "height": 7,
        "block_hash": "ab" * 32,
        "economic_state_root": economic_state_root(_state()),
    }


def test_returns_verified_canonical_bond_snapshot():
    result = get_settlement_bond_state(
        _state(),
        account_id="deltaalpha-settlement",
        correlation_id="corr-001",
        required_whz=Decimal("20"),
        chain_id="whalezchain-mainnet-v1",
        finalized_head=_head(),
        observed_at="2026-09-30T00:00:00+00:00",
    )

    assert result["status"] == "VERIFIED"
    assert result["available_whz"] == "75.00000000"
    assert result["locked_whz"] == "25.00000000"
    assert result["reserved_whz"] == "25.00000000"
    assert result["required_whz"] == "20.00000000"
    assert result["finalized_height"] == 7
    assert result["economic_state_root"] == economic_state_root(_state())
    assert result["bond_state_id"]


def test_insufficient_bond_is_fail_closed():
    with pytest.raises(
        SettlementBondStateError,
        match="settlement_whz_bond_insufficient",
    ) as exc_info:
        get_settlement_bond_state(
            _state(),
            account_id="deltaalpha-settlement",
            correlation_id="corr-002",
            required_whz="76",
            chain_id="whalezchain-mainnet-v1",
            finalized_head=_head(),
        )

    assert exc_info.value.status_code == 409


def test_read_is_non_mutating():
    state = _state()
    before = repr(state)

    get_settlement_bond_state(
        state,
        account_id="deltaalpha-settlement",
        correlation_id="corr-003",
        required_whz="20",
        chain_id="whalezchain-mainnet-v1",
        finalized_head=_head(),
    )

    assert repr(state) == before


def test_state_id_changes_when_required_bond_changes():
    first = get_settlement_bond_state(
        _state(),
        account_id="deltaalpha-settlement",
        correlation_id="corr-004",
        required_whz="20",
        chain_id="whalezchain-mainnet-v1",
        finalized_head=_head(),
        observed_at="2026-09-30T00:00:00+00:00",
    )
    second = get_settlement_bond_state(
        _state(),
        account_id="deltaalpha-settlement",
        correlation_id="corr-005",
        required_whz="30",
        chain_id="whalezchain-mainnet-v1",
        finalized_head=_head(),
        observed_at="2026-09-30T00:00:00+00:00",
    )

    assert first["bond_state_id"] != second["bond_state_id"]
