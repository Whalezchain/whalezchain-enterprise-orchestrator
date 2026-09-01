from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any


class ExecutionCertificateError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def certificate_hash(certificate: dict[str, Any]) -> str:
    unsigned = dict(certificate)
    verification = dict(unsigned.get("verification") or {})
    verification.pop("certificate_hash", None)
    unsigned["verification"] = verification
    return sha256(unsigned)


def verify_governance_verdict_signature(verdict: dict[str, Any], governance_key: str) -> bool:
    signature = (verdict.get("signatures") or {}).get("gov_signature") or {}
    if signature.get("alg") != "hmac-sha256" or not signature.get("sig"):
        return False
    unsigned = dict(verdict)
    unsigned.pop("signatures", None)
    expected = hmac.new(governance_key.encode(), canonical_json(unsigned), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature["sig"])


def verify_executor_signature(certificate: dict[str, Any], executor_key: str) -> bool:
    att = certificate.get("attestations") or {}
    ex = dict(att.get("executor") or {})
    supplied = ex.pop("signature", None)
    if ex.get("service") != "whalez-executor" or ex.get("algorithm") != "hmac-sha256" or not supplied:
        return False
    unsigned = dict(certificate)
    unsigned_att = dict(att)
    unsigned_att["executor"] = ex
    unsigned["attestations"] = unsigned_att
    verification = dict(unsigned.get("verification") or {})
    verification.pop("certificate_hash", None)
    unsigned["verification"] = verification
    expected = hmac.new(executor_key.encode(), canonical_json(unsigned), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied)


def verify_certificate(
    certificate: dict[str, Any],
    *,
    governance_key: str | None = None,
    executor_key: str | None = None,
) -> dict[str, Any]:
    if certificate.get("kind") != "wsp.execution_certificate":
        raise ExecutionCertificateError("Invalid execution certificate kind")
    if certificate.get("version") != "1.0":
        raise ExecutionCertificateError("Unsupported execution certificate version")

    execution = certificate.get("execution") or {}
    verdict = certificate.get("governance_verdict") or {}
    report = certificate.get("execution_report") or {}

    required = ["task_id", "intent_id", "correlation_id", "tool_id", "verb", "resource", "result_hash", "execution_report_hash"]
    missing = [name for name in required if not execution.get(name)]
    if missing:
        raise ExecutionCertificateError(f"Missing execution fields: {', '.join(missing)}")

    if verdict.get("kind") != "wsp.gov_verdict" or verdict.get("version") != "1.0":
        raise ExecutionCertificateError("Embedded governance verdict missing or invalid")
    if (verdict.get("decision") or {}).get("status") != "approved":
        raise ExecutionCertificateError("Execution certificate requires approved governance")
    if report.get("kind") != "wsp.execution_report":
        raise ExecutionCertificateError("Embedded execution report missing or invalid")

    vmeta = verdict.get("meta") or {}
    if vmeta.get("intent_id") != execution["intent_id"]:
        raise ExecutionCertificateError("Intent binding mismatch")
    if vmeta.get("correlation_id") != execution["correlation_id"]:
        raise ExecutionCertificateError("Correlation binding mismatch")

    rmeta = report.get("meta") or {}
    if rmeta.get("task_id") != execution["task_id"] or rmeta.get("intent_id") != execution["intent_id"]:
        raise ExecutionCertificateError("Execution report binding mismatch")

    if execution["execution_report_hash"] != sha256(report):
        raise ExecutionCertificateError("Execution report hash mismatch")
    if certificate.get("verification", {}).get("certificate_hash") != certificate_hash(certificate):
        raise ExecutionCertificateError("Execution certificate hash mismatch")

    if governance_key is not None and not verify_governance_verdict_signature(verdict, governance_key):
        raise ExecutionCertificateError("Governance verdict signature verification failed")
    if executor_key is not None and not verify_executor_signature(certificate, executor_key):
        raise ExecutionCertificateError("Executor signature verification failed")

    return {
        "valid": True,
        "certificate_id": certificate.get("certificate_id"),
        "task_id": execution["task_id"],
        "intent_id": execution["intent_id"],
        "correlation_id": execution["correlation_id"],
        "tool_id": execution["tool_id"],
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
