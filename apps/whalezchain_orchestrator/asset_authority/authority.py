from __future__ import annotations

from .assets import get_asset


class AssetAuthority:

    def validate(self, asset_symbol: str):
        return get_asset(asset_symbol)

    def metadata(self, asset_symbol: str):
        asset = get_asset(asset_symbol)

        return {
            "symbol": asset_symbol,
            **asset,
        }


asset_authority = AssetAuthority()
