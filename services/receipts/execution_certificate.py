from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any


class ExecutionCertificateError(ValueError):
    pass


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def certificate_hash(certificate: dict[str, Any]) -> str:
    unsigned = dict(certificate)
    verification = dict(unsigned.get("verification") or {})
    verification.pop("certificate_hash", None)
    unsigned["verification"] = verification
    return hashlib.sha256(_canonical_json(unsigned)).hexdigest()


def verify_governance_signature(
    certificate: dict[str, Any],
    governance_key: str,
) -> bool:
    authority = certificate.get("authority") or {}
    supplied = authority.get("governance_signature")
    verdict = {
        "kind": "wsp.gov_verdict",
        "version": "1.0",
        "meta": {
            "verdict_id": authority.get("governance_verdict_id"),
            "intent_id": (certificate.get("execution") or {}).get("intent_id"),
            "correlation_id": (certificate.get("execution") or {}).get("correlation_id"),
        },
        "decision": {
            "status": authority.get("decision"),
        },
        "policy": {
            "risk": authority.get("risk"),
            "checks": authority.get("governance_checks", []),
        },
    }
    expected = hmac.new(
        governance_key.encode("utf-8"),
        _canonical_json(verdict),
        hashlib.sha256,
    ).hexdigest()
    return bool(supplied) and hmac.compare_digest(expected, supplied)


def verify_certificate(
    certificate: dict[str, Any],
    *,
    governance_key: str | None = None,
    require_governance_signature: bool = True,
) -> dict[str, Any]:
    if certificate.get("kind") != "wsp.execution_certificate":
        raise ExecutionCertificateError("Invalid execution certificate kind")
    if certificate.get("version") != "1.0":
        raise ExecutionCertificateError("Unsupported execution certificate version")

    execution = certificate.get("execution") or {}
    authority = certificate.get("authority") or {}
    executor = certificate.get("executor") or {}
    verification = certificate.get("verification") or {}

    required = {
        "task_id", "intent_id", "correlation_id", "tool_id",
        "verb", "resource", "result_hash", "execution_report_hash",
    }
    missing = sorted(k for k in required if not execution.get(k))
    if missing:
        raise ExecutionCertificateError(
            f"Missing execution fields: {', '.join(missing)}"
        )

    if authority.get("decision") != "approved":
        raise ExecutionCertificateError("Execution certificate is not based on approved governance")
    if not authority.get("governance_verdict_id"):
        raise ExecutionCertificateError("Governance verdict id missing")
    if executor.get("service") != "whalez-executor":
        raise ExecutionCertificateError("Unexpected executor service")
    if not executor.get("executor_signature"):
        raise ExecutionCertificateError("Executor signature missing")

    expected_hash = certificate_hash(certificate)
    if verification.get("certificate_hash") != expected_hash:
        raise ExecutionCertificateError("Execution certificate hash mismatch")

    if require_governance_signature:
        if not governance_key:
            raise ExecutionCertificateError("Governance verification key is required")
        if not verify_governance_signature(certificate, governance_key):
            raise ExecutionCertificateError("Governance signature verification failed")

    return {
        "valid": True,
        "certificate_id": certificate.get("certificate_id"),
        "task_id": execution["task_id"],
        "intent_id": execution["intent_id"],
        "correlation_id": execution["correlation_id"],
        "tool_id": execution["tool_id"],
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
