from decimal import Decimal

import pytest

from ..mainnet.genesis_economic_state import (
    FOUNDER_ALLOCATION_WALLET,
    FOUNDER_EXTERNAL_WALLET,
    SYSTEM_POOL_WALLET,
    GenesisEconomicStateError,
    apply_user_deposit,
    economic_state_root,
    founder_external_unlock,
    initialize_genesis_economic_state,
    register_founder_wallets,
    system_to_founder_allocation,
    validate_genesis_economic_state,
)


def test_genesis_initializes_system_pool():
    state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000000"
    )

    assert state["system_pool"]["ptn"] == "1000000.00000000"
    assert state["founder"]["allocation_ptn"] == "0.00000000"
    assert state["founder"]["external_ptn"] == "0.00000000"


def test_founder_wallet_registration_is_non_monetary():
    state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000"
    )

    registered = register_founder_wallets(state)

    assert registered["system_pool"]["ptn"] == "1000.00000000"
    assert registered["founder"]["allocation_ptn"] == "0.00000000"
    assert registered["founder"]["external_ptn"] == "0.00000000"


def test_system_to_founder_allocation_preserves_supply():
    state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000"
    )

    result = system_to_founder_allocation(
        state,
        amount="250",
    )

    assert result["system_pool"]["ptn"] == "750.00000000"
    assert result["founder"]["allocation_ptn"] == "250.00000000"


def test_direct_system_to_external_is_not_exposed():
    state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000"
    )

    assert "external_ptn" not in state["system_pool"]


def test_founder_unlock_respects_alpha():
    state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000"
    )

    state = system_to_founder_allocation(
        state,
        amount="400",
    )

    state = founder_external_unlock(
        state,
        amount="200",
        founder_access_ratio="0.50",
    )

    assert state["founder"]["allocation_ptn"] == "200.00000000"
    assert state["founder"]["external_ptn"] == "200.00000000"


def test_founder_unlock_rejects_alpha_violation():
    state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000"
    )

    state = system_to_founder_allocation(
        state,
        amount="400",
    )

    with pytest.raises(GenesisEconomicStateError):
        founder_external_unlock(
            state,
            amount="201",
            founder_access_ratio="0.50",
        )


def test_deposit_always_enters_system_pool_and_splits_c_w():
    state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000"
    )

    result = apply_user_deposit(
        state,
        account_id="ALICE",
        account_level="L0",
        deposit="1000",
    )

    assert result["system_pool"]["ptn"] == "2000.00000000"
    assert result["accounts"]["ALICE"]["trading_capital"] == "900.00000000"
    assert result["accounts"]["ALICE"]["whz_bond"] == "100.00000000"

    total = (
        Decimal(result["accounts"]["ALICE"]["trading_capital"])
        + Decimal(result["accounts"]["ALICE"]["whz_bond"])
    )

    assert total == Decimal("1000")


def test_deposit_preserves_existing_locked_whz_bond():
    state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000"
    )

    state = apply_user_deposit(
        state,
        account_id="ALICE",
        account_level="L0",
        deposit="100",
    )

    # Simulate an already-established settlement lock.
    state["accounts"]["ALICE"]["whz_bond_locked"] = "5.00000000"

    result = apply_user_deposit(
        state,
        account_id="ALICE",
        account_level="L0",
        deposit="100",
    )

    assert result["accounts"]["ALICE"]["whz_bond"] == "20.00000000"
    assert result["accounts"]["ALICE"]["whz_bond_locked"] == "5.00000000"


def test_account_level_change_requires_governance():
    state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000"
    )

    state = apply_user_deposit(
        state,
        account_id="ALICE",
        account_level="L0",
        deposit="100",
    )

    with pytest.raises(GenesisEconomicStateError):
        apply_user_deposit(
            state,
            account_id="ALICE",
            account_level="L1",
            deposit="100",
        )


def test_economic_state_root_is_deterministic():
    state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000"
    )

    root1 = economic_state_root(state)
    root2 = economic_state_root(state)

    assert root1 == root2
    assert len(root1) == 64


def test_negative_balances_fail_validation():
    state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000"
    )

    state["system_pool"]["ptn"] = "-1"

    with pytest.raises(GenesisEconomicStateError):
        validate_genesis_economic_state(state)


def _test_genesis_fixture(economic_state):
    from ..mainnet.authentication import (
        derive_account_id,
        generate_keypair,
    )
    from ..mainnet.genesis import (
        GenesisValidator,
        build_genesis,
    )

    _, public_key = generate_keypair()
    public_bytes = public_key.public_bytes_raw()
    sender = derive_account_id(public_bytes)

    validator = GenesisValidator(
        validator_id=sender,
        public_key=public_bytes.hex(),
    )

    return build_genesis(
        genesis_timestamp="2026-01-01T00:00:00Z",
        initial_state={sender: {"PTN": "0"}},
        validators=[validator],
        authority_config={"mode": "test"},
        economic_state=economic_state,
    )


def _test_economic_state(ptn):
    return initialize_genesis_economic_state(
        ptn_genesis_supply=ptn,
    )


def test_genesis_economic_state_is_committed():
    from ..mainnet.genesis import verify_genesis

    economic = _test_economic_state("1000000.00000000")
    genesis = _test_genesis_fixture(economic)

    verify_genesis(genesis)

    assert genesis.economic_state == economic
    assert "economic_state" in genesis.unsigned_dict()
    assert "economic_state_root" in genesis.unsigned_dict()


def test_economic_state_changes_genesis_hash():
    first = _test_economic_state("1000000.00000000")
    second = _test_economic_state("2000000.00000000")

    genesis_a = _test_genesis_fixture(first)
    genesis_b = _test_genesis_fixture(second)

    assert genesis_a.economic_state != genesis_b.economic_state
    assert genesis_a.genesis_hash != genesis_b.genesis_hash


def test_tampered_genesis_economic_state_is_rejected():
    from copy import deepcopy
    from dataclasses import replace

    from ..mainnet.genesis import (
        GenesisValidationError,
        verify_genesis,
    )

    economic = _test_economic_state("1000000.00000000")
    genesis = _test_genesis_fixture(economic)

    tampered = deepcopy(genesis.economic_state)
    tampered["system_pool"]["ptn"] = "9999999.00000000"

    tampered_genesis = replace(
        genesis,
        economic_state=tampered,
    )

    with pytest.raises(GenesisValidationError):
        verify_genesis(tampered_genesis)
