from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)

from ..asset_authority import ASSET_REGISTRY
from .authentication import derive_account_id
from .genesis_economic_state import (
    canonical_economic_state,
    economic_state_root,
    empty_economic_state,
    validate_genesis_economic_state,
)
from .state_transition import BalanceState, state_root
from .transaction import canonical_json, sha256_hex


MAINNET_NETWORK_CLASS = "whalezchain_mainnet"
MAINNET_CHAIN_ID = "whalezchain-mainnet-v1"


class GenesisValidationError(ValueError):
    pass


@dataclass(frozen=True)
class GenesisValidator:
    validator_id: str
    public_key: str

    @property
    def account_id(self) -> str:
        try:
            public_key = bytes.fromhex(self.public_key)
        except ValueError as exc:
            raise GenesisValidationError(
                f"validator public key is not hexadecimal: "
                f"{self.validator_id}"
            ) from exc

        try:
            Ed25519PublicKey.from_public_bytes(public_key)
        except ValueError as exc:
            raise GenesisValidationError(
                f"invalid Ed25519 public key: {self.validator_id}"
            ) from exc

        return derive_account_id(public_key)


@dataclass(frozen=True)
class MainnetGenesis:
    chain_id: str
    network_class: str
    genesis_timestamp: str
    asset_registry: Dict[str, Dict[str, str]]
    initial_state: BalanceState
    economic_state: Dict[str, Any]
    authority_config: Dict[str, Any]
    validator_config: tuple[GenesisValidator, ...]
    state_root: str
    genesis_hash: str

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "network_class": self.network_class,
            "genesis_timestamp": self.genesis_timestamp,
            "asset_registry": deepcopy(self.asset_registry),
            "initial_state": deepcopy(self.initial_state),
            "economic_state": deepcopy(self.economic_state),
            "economic_state_root": economic_state_root(self.economic_state),
            "authority_config": deepcopy(self.authority_config),
            "validator_config": [
                {
                    "validator_id": validator.validator_id,
                    "public_key": validator.public_key,
                    "account_id": validator.account_id,
                }
                for validator in self.validator_config
            ],
            "state_root": self.state_root,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json(self.unsigned_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.unsigned_dict()
        result["genesis_hash"] = self.genesis_hash
        return result


def _validate_timestamp(timestamp: str) -> None:
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise GenesisValidationError(
            "genesis timestamp must be a non-empty string"
        )

    try:
        parsed = datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise GenesisValidationError(
            "genesis timestamp must be ISO-8601"
        ) from exc

    if parsed.tzinfo is None:
        raise GenesisValidationError(
            "genesis timestamp must include timezone"
        )

    if parsed.astimezone(timezone.utc).isoformat() != (
        timestamp.replace("Z", "+00:00")
    ):
        raise GenesisValidationError(
            "genesis timestamp must use canonical UTC representation"
        )


def _normalize_validators(
    validators: Iterable[GenesisValidator],
) -> tuple[GenesisValidator, ...]:
    normalized = tuple(validators)

    if not normalized:
        raise GenesisValidationError(
            "genesis requires at least one validator"
        )

    seen_ids: set[str] = set()
    seen_keys: set[str] = set()

    for validator in normalized:
        if not validator.validator_id:
            raise GenesisValidationError(
                "validator_id must not be empty"
            )

        if validator.validator_id in seen_ids:
            raise GenesisValidationError(
                f"duplicate validator_id: {validator.validator_id}"
            )

        if validator.public_key in seen_keys:
            raise GenesisValidationError(
                f"duplicate validator public key: "
                f"{validator.validator_id}"
            )

        # Forces cryptographic validation and canonical identity
        # derivation.
        validator.account_id

        seen_ids.add(validator.validator_id)
        seen_keys.add(validator.public_key)

    return tuple(
        sorted(
            normalized,
            key=lambda validator: validator.validator_id,
        )
    )


def build_genesis(
    *,
    genesis_timestamp: str,
    initial_state: BalanceState,
    validators: Iterable[GenesisValidator],
    authority_config: Dict[str, Any],
    chain_id: str = MAINNET_CHAIN_ID,
    network_class: str = MAINNET_NETWORK_CLASS,
    economic_state: Dict[str, Any] | None = None,
) -> MainnetGenesis:

    if chain_id != MAINNET_CHAIN_ID:
        raise GenesisValidationError(
            f"unsupported mainnet chain_id: {chain_id}"
        )

    if network_class != MAINNET_NETWORK_CLASS:
        raise GenesisValidationError(
            f"unsupported mainnet network_class: {network_class}"
        )

    _validate_timestamp(genesis_timestamp)

    validator_config = _normalize_validators(validators)
    state = deepcopy(initial_state)

    for account_id, account_state in state.items():
        if not account_id:
            raise GenesisValidationError(
                "initial state contains empty account id"
            )

        unknown_assets = set(account_state) - set(ASSET_REGISTRY)

        if unknown_assets:
            raise GenesisValidationError(
                f"initial state contains unknown assets: "
                f"{sorted(unknown_assets)}"
            )

    canonical_assets = deepcopy(ASSET_REGISTRY)
    canonical_state_root = state_root(state)
    canonical_economics = canonical_economic_state(
        economic_state if economic_state is not None else empty_economic_state()
    )
    validate_genesis_economic_state(canonical_economics)

    genesis = MainnetGenesis(
        chain_id=chain_id,
        network_class=network_class,
        genesis_timestamp=genesis_timestamp,
        asset_registry=canonical_assets,
        initial_state=state,
        economic_state=canonical_economics,
        authority_config=deepcopy(authority_config),
        validator_config=validator_config,
        state_root=canonical_state_root,
        genesis_hash="",
    )

    genesis_hash = sha256_hex(genesis.unsigned_dict())

    return MainnetGenesis(
        chain_id=genesis.chain_id,
        network_class=genesis.network_class,
        genesis_timestamp=genesis.genesis_timestamp,
        asset_registry=deepcopy(genesis.asset_registry),
        initial_state=deepcopy(genesis.initial_state),
        economic_state=deepcopy(genesis.economic_state),
        authority_config=deepcopy(genesis.authority_config),
        validator_config=genesis.validator_config,
        state_root=genesis.state_root,
        genesis_hash=genesis_hash,
    )


def verify_genesis(genesis: MainnetGenesis) -> None:
    _validate_timestamp(genesis.genesis_timestamp)
    _normalize_validators(genesis.validator_config)

    expected_state_root = state_root(genesis.initial_state)
    canonical_economics = canonical_economic_state(genesis.economic_state)
    validate_genesis_economic_state(canonical_economics)
    expected_economic_root = economic_state_root(canonical_economics)

    if expected_state_root != genesis.state_root:
        raise GenesisValidationError(
            "genesis state_root does not match initial_state"
        )

    if genesis.economic_state != canonical_economics:
        raise GenesisValidationError(
            "genesis economic_state is not canonical"
        )

    if economic_state_root(genesis.economic_state) != expected_economic_root:
        raise GenesisValidationError(
            "genesis economic_state_root does not match economic_state"
        )

    if genesis.asset_registry != ASSET_REGISTRY:
        raise GenesisValidationError(
            "genesis asset registry does not match canonical asset authority"
        )

    expected_hash = sha256_hex(genesis.unsigned_dict())

    if expected_hash != genesis.genesis_hash:
        raise GenesisValidationError(
            "genesis hash verification failed"
        )
