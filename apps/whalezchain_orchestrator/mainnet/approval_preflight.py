"""Native, read-only Founder-approval preflight.

Cryptographically verifies a specific canonical settlement candidate against
an independently enrolled Ed25519 key and pinned ROOT revision. It NEVER
authorizes settlement, consumes a nonce, unlocks a hold, or claims finality.

The trust document is private, owner-only, externally provisioned, and disabled
until configured. Caller-supplied "role"/"approved" fields grant nothing.
"""
from __future__ import annotations

import json
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .approval_provenance import (
    ApprovalProvenanceError,
    parse_signed_receipt,
    verify_receipt,
)
from .transaction import sha256_hex


REQUIRED_TRUST_FIELDS = frozenset({
    "schema", "enrolled_key_id", "enrolled_public_key_hex",
    "effective_root_pins", "revoked_key_ids", "approved_chain_id",
})
TRUST_SCHEMA = "whalezchain.private.approval_verification_context.v1"
EXPECTED_SCOPE = "whalezchain.mainnet.external_settlement.finalize"


class ApprovalPreflightError(ValueError):
    pass


def _no_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ApprovalPreflightError("duplicated_trusted_config_key")
        result[key] = value
    return result


def load_trusted_context(path: str | Path | None = None) -> dict[str, Any]:
    """Load verified pins from private operator-controlled file; never request JSON."""
    resolved = Path(path) if path is not None else Path(
        os.getenv("WHALEZCHAIN_APPROVAL_TRUST_CONTEXT_FILE", "")
    )
    if not str(resolved) or str(resolved) == "." or not resolved.is_absolute():
        raise ApprovalPreflightError("trusted_approval_context_not_configured")
    if resolved.is_symlink():
        raise ApprovalPreflightError("trusted_context_symlink_disallowed")
    try:
        info = resolved.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ApprovalPreflightError("trusted_context_owner_or_type_invalid")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise ApprovalPreflightError("trusted_context_permissions_too_broad")
        if info.st_size < 50 or info.st_size > 8192:
            raise ApprovalPreflightError("trusted_context_size_invalid")
        config = json.loads(resolved.read_text("utf-8"),
                            object_pairs_hook=_no_duplicate_json_keys)
    except OSError as exc:
        raise ApprovalPreflightError("trusted_context_unavailable") from exc
    except (ValueError, TypeError) as exc:
        raise ApprovalPreflightError("trusted_context_invalid_json") from exc
    if type(config) is not dict or set(config) != REQUIRED_TRUST_FIELDS:
        raise ApprovalPreflightError("trusted_context_field_mismatch")
    if config["schema"] != TRUST_SCHEMA:
        raise ApprovalPreflightError("trusted_context_schema_invalid")
    if (type(config["enrolled_public_key_hex"]) is not str
        or len(config["enrolled_public_key_hex"]) != 64
        or type(config["enrolled_key_id"]) is not str
        or not config["enrolled_key_id"]
        or type(config["approved_chain_id"]) is not str
        or not config["approved_chain_id"]
        or type(config["revoked_key_ids"]) is not list
        or any(type(x) is not str for x in config["revoked_key_ids"])
        or len(set(config["revoked_key_ids"])) != len(config["revoked_key_ids"])):
        raise ApprovalPreflightError("trusted_context_values_invalid")
    pins = config["effective_root_pins"]
    required = {"governance_sha256","change_control_sha256","genesis_registry_sha256"}
    if (type(pins) is not dict or set(pins) != required or any(
        type(v) is not str or len(v) != 64 or
        any(ch not in "0123456789abcdef" for ch in v) or
        v in {"0"*64, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}
        for v in pins.values()
    )):
        raise ApprovalPreflightError("effective_root_pins_missing_or_unratified")
    # Existence of this file is not proof the ROOT approval procedure occurred.
    return config


def exact_settlement_payload(finalization_payload: Mapping[str, Any],
                             settlement: Mapping[str, Any]) -> dict[str, Any]:
    if type(finalization_payload) is not dict or type(settlement) is not dict:
        raise ApprovalPreflightError("canonical_settlement_missing")
    if not finalization_payload or not settlement:
        raise ApprovalPreflightError("canonical_settlement_missing")
    if (finalization_payload.get("authorization_type") !=
        "wcz.mainnet.finalization_authorization.v1"):
        raise ApprovalPreflightError("finalization_type_mismatch")
    target = finalization_payload.get("target_payload_hash")
    if type(target) is not str or len(target) != 64 or target != sha256_hex({
        k: v for k,v in finalization_payload.items() if k != "target_payload_hash"
    }):
        raise ApprovalPreflightError("finalization_hash_mismatch")
    if settlement.get("user_id") in (None,"") or type(settlement.get("amount_minor")) is not int:
        raise ApprovalPreflightError("canonical_settlement_beneficiary_or_amount_missing")
    if settlement["amount_minor"] <= 0:
        raise ApprovalPreflightError("canonical_settlement_amount_invalid")
    return {
        "scope": EXPECTED_SCOPE,
        "target_sha256": target,
        "amount_minor": settlement["amount_minor"],
        "beneficiary": settlement["user_id"],
        "finalization_payload": dict(finalization_payload),
        "external_settlement": dict(settlement),
    }


def preflight_signed_settlement(
    *,
    signed_receipt_json: str,
    expected_approval_id: str,
    expected_chain_id: str,
    finalization_payload: dict[str, Any],
    settlement: dict[str, Any],
    trusted_context: dict[str, Any] | None = None,
    now: int | None = None,
) -> dict[str, Any]:
    context = trusted_context if trusted_context is not None else load_trusted_context()
    if type(context) is not dict or set(context) != REQUIRED_TRUST_FIELDS:
        raise ApprovalPreflightError("trusted_context_not_enrolled")
    if expected_chain_id != context["approved_chain_id"]:
        raise ApprovalPreflightError("chain_not_approved_by_private_context")
    if (finalization_payload.get("chain_id") != expected_chain_id
            or finalization_payload.get("approval_id") != expected_approval_id):
        raise ApprovalPreflightError("candidate_chain_or_approval_mismatch")
    exact = exact_settlement_payload(finalization_payload, settlement)
    try:
        receipt = parse_signed_receipt(signed_receipt_json)
        verified = verify_receipt(
            receipt,
            enrolled_public_key_hex=context["enrolled_public_key_hex"],
            enrolled_key_id=context["enrolled_key_id"],
            expected_approval_id=expected_approval_id,
            execution_payload=exact,
            expected_chain_id=expected_chain_id,
            effective_root_pins=context["effective_root_pins"],
            revoked_key_ids=frozenset(context["revoked_key_ids"]),
            now=int(time.time()) if now is None else now,
        )
    except ApprovalProvenanceError as exc:
        raise ApprovalPreflightError("signed_approval_provenance_invalid") from exc
    # CRITICAL: This does NOT atomically consume approval nonce or state.
    return {
        "approval_provenance_verified": True,
        "approval_id": verified["approval_id"],
        "receipt_sha256": verified["receipt_sha256"],
        "execution_payload_sha256": verified["execution_payload_sha256"],
        "nonce_sha256": verified["nonce_sha256"],
        "atomic_nonce_consumption_verified": False,
        "custody_enrollment_verified": False,
        "quorum_finality_verified": False,
        "independent_restore_verified": False,
        "financial_execution_authorized": False,
        "mainnet_activation_authorized": False,
    }


def require_atomic_financial_release() -> None:
    """Release gate intentionally CLOSED until a reviewed atomic protocol exists.

    Do not replace this with an env toggle or a model-generated 'approved' field.
    """
    raise ApprovalPreflightError("atomic_approval_consumption_and_independent_finality_not_certified")