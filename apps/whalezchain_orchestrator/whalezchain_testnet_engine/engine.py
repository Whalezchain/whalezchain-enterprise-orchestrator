from __future__ import annotations

import hashlib
import json

from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List

from .state import (
    load_accounts,
    load_journal,
    save_accounts,
    append_journal,
    save_metadata,
    save_state_root,
)

from ..asset_authority import ASSET_REGISTRY

ASSETS = ASSET_REGISTRY

BOUNDARIES: Dict[str, bool] = {
    "mainnet": False,
    "real_funds": False,
    "custody": False,
    "trading": False,
    "settlement": False,
    "source_change": False,
    "authority_change": False,
    "external_consensus_claim": False,
    "validator_finality_claim": False,
}


def canonical_json(obj: Any) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha_obj(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj)).hexdigest()


def decimal_str(value: str | Decimal) -> str:
    return f"{Decimal(str(value)):.8f}"


@dataclass
class WhalezchainTestnetEngine:
    network_class: str = "internal_whalezchain_testnet"

    accounts: Dict[str, Dict[str, str]] = field(
        default_factory=load_accounts
    )

    journal: List[Dict[str, Any]] = field(
        default_factory=load_journal
    )

    def reload(self) -> None:
        self.accounts = load_accounts()
        self.journal = load_journal()

    def ensure_account(self, account_id: str) -> None:
        if account_id not in self.accounts:
            self.accounts[account_id] = {
                symbol: "0.00000000"
                for symbol in ASSETS
            }

    def _persist(self) -> None:
        save_accounts(self.accounts)

        save_state_root(
            self.state_root()
        )

        save_metadata({
            "network_class": self.network_class,
            "journal_entries": len(self.journal),
            "last_state_root": self.state_root(),
        })

    def credit(
        self,
        account_id: str,
        asset_symbol: str,
        amount: str,
        reason: str,
    ) -> Dict[str, Any]:

        self._validate_asset(asset_symbol)

        self.ensure_account(account_id)

        before_root = self.state_root()

        old_balance = Decimal(
            self.accounts[account_id][asset_symbol]
        )

        new_balance = old_balance + Decimal(amount)

        self.accounts[account_id][asset_symbol] = decimal_str(
            new_balance
        )

        tx = {
            "tx_type": "internal_testnet_credit",
            "network_class": self.network_class,
            "account_id": account_id,
            "asset_symbol": asset_symbol,
            "canonical_asset_name": ASSETS[asset_symbol]["canonical_asset_name"],
            "amount": decimal_str(amount),
            "reason": reason,
            "before_state_root": before_root,
            "after_state_root": self.state_root(),
            "balance_effect": True,
            "transfer_effect": False,
            "testnet_only": True,
            "boundaries": deepcopy(BOUNDARIES),
        }

        tx["tx_hash"] = sha_obj(
            {k: v for k, v in tx.items() if k != "tx_hash"}
        )

        self.journal.append(tx)

        append_journal(tx)

        self._persist()

        return tx

    def transfer(
        self,
        from_account: str,
        to_account: str,
        asset_symbol: str,
        amount: str,
    ) -> Dict[str, Any]:

        self._validate_asset(asset_symbol)

        self.ensure_account(from_account)
        self.ensure_account(to_account)

        before_root = self.state_root()

        amt = Decimal(amount)

        from_balance = Decimal(
            self.accounts[from_account][asset_symbol]
        )

        if from_balance < amt:
            raise ValueError(
                f"insufficient internal testnet balance: {from_account} {asset_symbol}"
            )

        self.accounts[from_account][asset_symbol] = decimal_str(
            from_balance - amt
        )

        self.accounts[to_account][asset_symbol] = decimal_str(
            Decimal(
                self.accounts[to_account][asset_symbol]
            ) + amt
        )

        tx = {
            "tx_type": "internal_testnet_transfer",
            "network_class": self.network_class,
            "from_account": from_account,
            "to_account": to_account,
            "asset_symbol": asset_symbol,
            "canonical_asset_name": ASSETS[asset_symbol]["canonical_asset_name"],
            "amount": decimal_str(amount),
            "before_state_root": before_root,
            "after_state_root": self.state_root(),
            "balance_effect": True,
            "transfer_effect": True,
            "testnet_only": True,
            "boundaries": deepcopy(BOUNDARIES),
        }

        tx["tx_hash"] = sha_obj(
            {k: v for k, v in tx.items() if k != "tx_hash"}
        )

        self.journal.append(tx)

        append_journal(tx)

        self._persist()

        return tx

    def state(self) -> Dict[str, Any]:
        return {
            "network_class": self.network_class,
            "accounts": deepcopy(self.accounts),
            "assets": deepcopy(ASSETS),
            "journal_count": len(self.journal),
            "journal_hashes": [
                entry["tx_hash"]
                for entry in self.journal
            ],
            "boundaries": deepcopy(BOUNDARIES),
        }

    def state_root(self) -> str:
        return sha_obj({
            "network_class": self.network_class,
            "accounts": self.accounts,
            "assets": ASSETS,
        })

    def receipt(self) -> Dict[str, Any]:
        receipt = {
            "receipt_type": "whalezchain_internal_testnet_balance_engine_receipt",
            "network_class": self.network_class,
            "state_root": self.state_root(),
            "journal_count": len(self.journal),
            "journal_hashes": [
                entry["tx_hash"]
                for entry in self.journal
            ],
            "asset_authority_snapshot": deepcopy(ASSETS),
            "boundaries": deepcopy(BOUNDARIES),
        }

        receipt["receipt_hash"] = sha_obj(
            {k: v for k, v in receipt.items() if k != "receipt_hash"}
        )

        return receipt

    def _validate_asset(self, asset_symbol: str) -> None:
        if asset_symbol not in ASSETS:
            raise ValueError(
                f"unsupported internal testnet asset: {asset_symbol}"
            )
