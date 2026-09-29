from decimal import Decimal

import pytest

from whalezchain_orchestrator.mainnet.economic_policy import (
    EconomicPolicyError,
    get_account_level,
    split_deposit,
    validate_founder_external_unlock,
)


@pytest.mark.parametrize(
    ("level", "deposit", "expected_capital", "expected_whz"),
    [
        ("L0", "1000", "900", "100"),
        ("L1", "1000", "800", "200"),
        ("L2", "1000", "700", "300"),
        ("L3", "1000", "600", "400"),
    ],
)
def test_genesis_deposit_split(
    level,
    deposit,
    expected_capital,
    expected_whz,
):
    result = split_deposit(
        deposit,
        account_level=level,
    )

    assert result["trading_capital"] == Decimal(expected_capital)
    assert result["whz_bond"] == Decimal(expected_whz)
    assert (
        result["trading_capital"] + result["whz_bond"]
        == result["deposit"]
    )


def test_unknown_account_level_rejected():
    with pytest.raises(EconomicPolicyError):
        get_account_level("L99")


def test_zero_deposit_rejected():
    with pytest.raises(EconomicPolicyError):
        split_deposit("0", account_level="L0")


def test_founder_external_unlock_respects_ratio():
    validate_founder_external_unlock(
        allocation_balance=Decimal("1000"),
        external_balance=Decimal("500"),
        founder_access_ratio=Decimal("0.50"),
    )


def test_founder_external_unlock_exceeding_ratio_rejected():
    with pytest.raises(EconomicPolicyError):
        validate_founder_external_unlock(
            allocation_balance=Decimal("1000"),
            external_balance=Decimal("501"),
            founder_access_ratio=Decimal("0.50"),
        )
