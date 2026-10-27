"""Monetary invariants using deterministic test-only signing keys."""
from dataclasses import replace
from decimal import Decimal
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from apps.whalezchain_orchestrator.mainnet.authentication import derive_account_id, sign_transaction
from apps.whalezchain_orchestrator.mainnet.issuance_policy import PRNIssuancePolicy
from apps.whalezchain_orchestrator.mainnet.state_transition import MainnetStateTransition
from apps.whalezchain_orchestrator.mainnet.transaction import MainnetTransaction
from apps.whalezchain_orchestrator.mainnet.transaction_validator import TransactionValidationError

CHAIN = "whalezchain-mainnet-v1"
# These fixed keys are fixtures only. They are never production wallet keys.
ALICE_KEY = Ed25519PrivateKey.from_private_bytes(bytes([17]) * 32)
BOB_KEY = Ed25519PrivateKey.from_private_bytes(bytes([29]) * 32)
ALICE = derive_account_id(ALICE_KEY.public_key().public_bytes_raw())
BOB = derive_account_id(BOB_KEY.public_key().public_bytes_raw())


def signed(*, recipient=BOB, amount="1.00000000", asset="WHZ", kind="transfer"):
    tx = MainnetTransaction(chain_id=CHAIN, tx_id="balance-conservation-fixture",
                           sender=ALICE, recipient=recipient, asset_symbol=asset,
                           amount=amount, nonce=0, transaction_type=kind,
                           authorization={"scheme": "ed25519-v1", "public_key": ALICE_KEY.public_key().public_bytes_raw().hex()},
                           ordering_key="000001")
    return replace(tx, authorization=sign_transaction(tx, ALICE_KEY))


def balances(whz="10.00000000"):
    return {ALICE: {"WHZ": whz, "PTN": "0.00000000", "PRN": "0.00000000"}}


class BalanceConservationTests(unittest.TestCase):
    def test_self_transfer_preserves_balance_and_root(self):
        original = balances()
        result = MainnetStateTransition().apply(original, [signed(recipient=ALICE)], chain_id=CHAIN)
        self.assertEqual(result["state"][ALICE]["WHZ"], "10.00000000")
        self.assertEqual(result["transitions"][0]["before_state_root"], result["transitions"][0]["after_state_root"])
        self.assertEqual(original, balances())

    def test_absent_sender_cannot_create_spendable_recipient_balance(self):
        original = {}
        with self.assertRaises(TransactionValidationError):
            MainnetStateTransition().apply(original, [signed()], chain_id=CHAIN)
        self.assertEqual(original, {})

    def test_absent_sender_self_transfer_is_rejected(self):
        with self.assertRaises(TransactionValidationError):
            MainnetStateTransition().apply({}, [signed(recipient=ALICE)], chain_id=CHAIN)

    def test_insufficient_existing_sender_is_rejected(self):
        with self.assertRaises(TransactionValidationError):
            MainnetStateTransition().apply(balances("0.00000000"), [signed()], chain_id=CHAIN)

    def test_distinct_accounts_preserve_total_supply(self):
        result = MainnetStateTransition().apply(balances(), [signed(amount="3.00000000")], chain_id=CHAIN)
        self.assertEqual(result["state"][ALICE]["WHZ"], "7.00000000")
        self.assertEqual(result["state"][BOB]["WHZ"], "3.00000000")
        self.assertEqual(sum(Decimal(a.get("WHZ", "0")) for a in result["state"].values()), Decimal("10"))

    def test_explicitly_authorized_prn_issuance_keeps_its_separate_semantics(self):
        policy = PRNIssuancePolicy(authorized_issuers=frozenset({ALICE}), max_supply=Decimal("5"))
        result = MainnetStateTransition().apply({}, [signed(asset="PRN", kind="mint_prn", amount="5.00000000")],
                                              chain_id=CHAIN, issuance_policy=policy)
        self.assertEqual(result["state"][BOB]["PRN"], "5.00000000")
        self.assertNotIn(ALICE, result["state"])


if __name__ == "__main__":
    unittest.main()
