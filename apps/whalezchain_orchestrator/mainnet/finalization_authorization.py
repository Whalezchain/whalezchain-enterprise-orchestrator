from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .transaction import sha256_hex


FINALIZATION_AUTHORIZATION_TYPE = (
    "wcz.mainnet.finalization_authorization.v1"
)


class FinalizationAuthorizationError(ValueError):
    pass


@dataclass(frozen=True)
class MainnetFinalizationAuthorization:
    """
    Exact-block authorization handoff produced by the trusted
    Whalez-AI execution boundary.

    This object does NOT establish Founder authority itself.
    Founder signature/approval verification occurs upstream in
    whalez-ai-control execution_gate.py.

    WhalezChain verifies that the resulting authorization binds
    exactly to the canonical block commitment it is being asked
    to finalize.
    """

    authorization_type: str
    approval_id: str
    execution_hash: str
    target_payload_hash: str
    chain_id: str
    genesis_hash: str
    height: int
    previous_block_hash: str
    transaction_root: str
    resulting_state_root: str
    economic_state_root: str
    block_hash: str
    authority: str
    execution_mode: str = "mainnet_finalization"

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "authorization_type": self.authorization_type,
            "approval_id": self.approval_id,
            "execution_hash": self.execution_hash,
            "target_payload_hash": self.target_payload_hash,
            "chain_id": self.chain_id,
            "genesis_hash": self.genesis_hash,
            "height": self.height,
            "previous_block_hash": self.previous_block_hash,
            "transaction_root": self.transaction_root,
            "resulting_state_root": self.resulting_state_root,
            "economic_state_root": self.economic_state_root,
            "block_hash": self.block_hash,
            "authority": self.authority,
            "execution_mode": self.execution_mode,
        }

    @property
    def authorization_hash(self) -> str:
        return sha256_hex(self.unsigned_dict())

    def verify_structure(self) -> None:
        if self.authorization_type != FINALIZATION_AUTHORIZATION_TYPE:
            raise FinalizationAuthorizationError(
                "invalid finalization authorization type"
            )

        if not self.approval_id:
            raise FinalizationAuthorizationError(
                "missing approval_id"
            )

        if not self.execution_hash:
            raise FinalizationAuthorizationError(
                "missing execution_hash"
            )

        if not self.target_payload_hash:
            raise FinalizationAuthorizationError(
                "missing target_payload_hash"
            )

        if not self.chain_id:
            raise FinalizationAuthorizationError(
                "missing chain_id"
            )

        if not self.genesis_hash:
            raise FinalizationAuthorizationError(
                "missing genesis_hash"
            )

        if self.height < 0:
            raise FinalizationAuthorizationError(
                "height must be non-negative"
            )

        if not self.previous_block_hash and self.height != 0:
            raise FinalizationAuthorizationError(
                "non-genesis finalization requires previous_block_hash"
            )

        if not self.transaction_root:
            raise FinalizationAuthorizationError(
                "missing transaction_root"
            )

        if not self.resulting_state_root:
            raise FinalizationAuthorizationError(
                "missing resulting_state_root"
            )

        if not self.economic_state_root:
            raise FinalizationAuthorizationError(
                "missing economic_state_root"
            )

        if not self.block_hash:
            raise FinalizationAuthorizationError(
                "missing block_hash"
            )

        if self.authority != "WHALEZ_AI":
            raise FinalizationAuthorizationError(
                "invalid execution authority"
            )

        if self.execution_mode != "mainnet_finalization":
            raise FinalizationAuthorizationError(
                "invalid execution mode"
            )

    def matches_block(
        self,
        *,
        chain_id: str,
        genesis_hash: str,
        height: int,
        previous_block_hash: str,
        transaction_root: str,
        resulting_state_root: str,
        economic_state_root: str,
        block_hash: str,
    ) -> None:
        self.verify_structure()

        expected = {
            "chain_id": chain_id,
            "genesis_hash": genesis_hash,
            "height": height,
            "previous_block_hash": previous_block_hash,
            "transaction_root": transaction_root,
            "resulting_state_root": resulting_state_root,
            "economic_state_root": economic_state_root,
            "block_hash": block_hash,
        }

        authorized = {
            "chain_id": self.chain_id,
            "genesis_hash": self.genesis_hash,
            "height": self.height,
            "previous_block_hash": self.previous_block_hash,
            "transaction_root": self.transaction_root,
            "resulting_state_root": self.resulting_state_root,
            "economic_state_root": self.economic_state_root,
            "block_hash": self.block_hash,
        }

        if authorized != expected:
            raise FinalizationAuthorizationError(
                "finalization authorization does not match "
                "candidate block"
            )


def build_finalization_payload(
    *,
    approval_id: str,
    execution_hash: str,
    chain_id: str,
    genesis_hash: str,
    height: int,
    previous_block_hash: str,
    transaction_root: str,
    resulting_state_root: str,
    economic_state_root: str,
    block_hash: str,
) -> dict[str, Any]:
    """
    Build the exact payload that the trusted execution boundary
    must authorize.

    The returned object is intentionally compatible with the
    existing execution_gate.py payload_hash mechanism.
    """

    payload = {
        "authorization_type": FINALIZATION_AUTHORIZATION_TYPE,
        "approval_id": approval_id,
        "execution_hash": execution_hash,
        "chain_id": chain_id,
        "genesis_hash": genesis_hash,
        "height": height,
        "previous_block_hash": previous_block_hash,
        "transaction_root": transaction_root,
        "resulting_state_root": resulting_state_root,
        "economic_state_root": economic_state_root,
        "block_hash": block_hash,
        "authority": "WHALEZ_AI",
        "execution_mode": "mainnet_finalization",
    }

    payload["target_payload_hash"] = sha256_hex(payload)

    return payload


def from_execution_authorization(
    authorization: dict[str, Any],
    *,
    finalization_payload: dict[str, Any],
) -> MainnetFinalizationAuthorization:
    """
    Convert the already-verified execution-gate result into the
    WhalezChain finalization authorization handoff.

    The caller must only invoke this after execution_gate.py has
    successfully verified Founder authorization.
    """

    if not isinstance(authorization, dict):
        raise FinalizationAuthorizationError(
            "execution authorization must be an object"
        )

    required = (
        "approval_id",
        "execution_hash",
        "target_payload_hash",
    )

    for key in required:
        if not authorization.get(key):
            raise FinalizationAuthorizationError(
                f"execution authorization missing {key}"
            )

    unsigned_payload = {
        key: value
        for key, value in finalization_payload.items()
        if key != "target_payload_hash"
    }
    expected_target_hash = sha256_hex(unsigned_payload)

    if authorization["target_payload_hash"] != expected_target_hash:
        raise FinalizationAuthorizationError(
            "execution authorization target hash does not "
            "match finalization payload"
        )

    return MainnetFinalizationAuthorization(
        authorization_type=FINALIZATION_AUTHORIZATION_TYPE,
        approval_id=str(authorization["approval_id"]),
        execution_hash=str(authorization["execution_hash"]),
        target_payload_hash=str(
            authorization["target_payload_hash"]
        ),
        chain_id=str(finalization_payload["chain_id"]),
        genesis_hash=str(finalization_payload["genesis_hash"]),
        height=int(finalization_payload["height"]),
        previous_block_hash=str(
            finalization_payload["previous_block_hash"]
        ),
        transaction_root=str(
            finalization_payload["transaction_root"]
        ),
        resulting_state_root=str(
            finalization_payload["resulting_state_root"]
        ),
        economic_state_root=str(
            finalization_payload["economic_state_root"]
        ),
        block_hash=str(finalization_payload["block_hash"]),
        authority=str(finalization_payload["authority"]),
        execution_mode=str(
            finalization_payload["execution_mode"]
        ),
    )
