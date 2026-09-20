import pytest
from unittest.mock import patch

from whalezchain_orchestrator.models import TestnetTransferRequest
from whalezchain_orchestrator.services.whalezchain_service import execute_transfer


SOURCE = "whalezchain-testnet://founder/internal-alpha"
DESTINATION = "whalezchain-testnet://validator/internal-beta"


@pytest.mark.parametrize(
    "amount, expected_error",
    [
        ("-1.00000000", "amount must be greater than zero"),
        ("0", "amount must be greater than zero"),
        ("Infinity", "amount must be a finite decimal"),
        ("-Infinity", "amount must be a finite decimal"),
    ],
)
def test_execute_transfer_rejects_invalid_amounts_before_engine(
    amount,
    expected_error,
):
    request = TestnetTransferRequest(
        from_account=SOURCE,
        to_account=DESTINATION,
        asset_symbol="PTN",
        amount=amount,
    )

    with patch(
        "whalezchain_orchestrator.services.whalezchain_service.engine.transfer"
    ) as transfer:
        with pytest.raises(ValueError, match=expected_error):
            execute_transfer(request)

        transfer.assert_not_called()
