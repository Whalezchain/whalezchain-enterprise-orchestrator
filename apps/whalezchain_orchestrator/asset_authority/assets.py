from __future__ import annotations

from typing import Dict


ASSET_REGISTRY: Dict[str, Dict[str, str]] = {
    "PTN": {
        "canonical_asset_name": "Plutonium",
        "asset_role_class": "platform_trade_note",
        "identity_status": "CANONICAL",
    },
    "PRN": {
        "canonical_asset_name": "Plutoranium",
        "asset_role_class": "platform_receipt_note",
        "identity_status": "CANONICAL",
    },
    "WHZ": {
        "canonical_asset_name": "Whalez-Mint",
        "asset_role_class": "ecosystem_policy_unit",
        "identity_status": "CANONICAL",
    },
}


def get_asset(asset_symbol: str) -> Dict[str, str]:
    if asset_symbol not in ASSET_REGISTRY:
        raise ValueError(
            f"unknown asset authority symbol: {asset_symbol}"
        )

    return ASSET_REGISTRY[asset_symbol]


def list_assets():
    return ASSET_REGISTRY.copy()
