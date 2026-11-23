"""Native receipt preflight tests; NO financial execution.

Uses independent TEST Ed25519 signing keys and isolated temporary chain state.
Production trust enrollment, ROOT ratification and atomic finality are absent.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from copy import deepcopy

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from whalezchain_orchestrator.main import app
from whalezchain_orchestrator.mainnet.approval_provenance import canonical_json, signing_bytes
from whalezchain_orchestrator.mainnet.approval_preflight import (
    ApprovalPreflightError, TRUST_SCHEMA, EXPECTED_SCOPE,
    exact_settlement_payload, load_trusted_context, preflight_signed_settlement,
)
from whalezchain_orchestrator.mainnet.external_settlement import (
    ExternalSettlementError, _build_request,
    prepare_external_settlement, preflight_external_settlement_approval,
    finalize_external_settlement,
)
from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore

from whalezchain_orchestrator.tests.test_external_settlement import _genesis, _payload


TEST_SIGNER = Ed25519PrivateKey.from_private_bytes(bytes([23]) * 32)
ROOT_PINS = {
    "governance_sha256": "a" * 64,
    "change_control_sha256": "b" * 64,
    "genesis_registry_sha256": "c" * 64,
}


def _config(*, revoked=None, pins=None):
    return {
        "schema": TRUST_SCHEMA,
        "enrolled_key_id": "test-independent-founder-key-not-enrolled",
        "enrolled_public_key_hex": TEST_SIGNER.public_key().public_bytes_raw().hex(),
        "effective_root_pins": pins if pins is not None else ROOT_PINS,
        "revoked_key_ids": revoked if revoked is not None else [],
        "approved_chain_id": "whalezchain-mainnet-v1",
    }


def _set_context(monkeypatch, tmp_path, **changes):
    trust = _config(**changes)
    path = tmp_path / "private_approval_test_context.json"
    path.write_text(json.dumps(trust), encoding="utf-8")
    os.chmod(path, 0o600)
    monkeypatch.setenv("WHALEZCHAIN_APPROVAL_TRUST_CONTEXT_FILE", str(path))
    return path


def _seed(monkeypatch, tmp_path):
    root = tmp_path / "canonical_chain"
    monkeypatch.setenv("WHALEZCHAIN_MAINNET_STORE_PATH", str(root))
    monkeypatch.setenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", "true")
    store = MainnetChainStore(root)
    store.initialize_genesis(_genesis())
    request = _payload()
    prepared = prepare_external_settlement(request)
    return store, request, prepared


def _receipt(request, prepared, *, mutate=None, expiration=None):
    final = prepared["finalization_payload"]
    execution = exact_settlement_payload(final, _build_request(request).canonical_dict())
    issued = int(time.time()) - 2
    body = {
        "schema": "whalez.founder.approval.receipt.v1",
        "approval_id": request["approval_id"],
        "approved_by": "FOUNDER",
        "authority": "FOUNDER_CONSOLE",
        "decision": "approved",
        "scope": EXPECTED_SCOPE,
        "chain_id": final["chain_id"],
        "execution_payload_sha256": hashlib.sha256(canonical_json(execution)).hexdigest(),
        "target_sha256": execution["target_sha256"],
        "root_pins": deepcopy(ROOT_PINS),
        "signer_key_id": "test-independent-founder-key-not-enrolled",
        "nonce_sha256": "e" * 64,
        "issued_at": issued,
        "expires_at": expiration if expiration is not None else issued + 120,
    }
    if mutate:
        body.update(mutate)
    return json.dumps({**body, "signature_hex": TEST_SIGNER.sign(signing_bytes(body)).hex()},
                      sort_keys=True)


def _native_payload(request, prepared, signed):
    return {
        **request, **prepared,
        "signed_approval_receipt_json": signed,
    }


def test_private_context_required_even_when_receipt_is_signed(monkeypatch, tmp_path):
    store, req, prepared = _seed(monkeypatch, tmp_path)
    monkeypatch.delenv("WHALEZCHAIN_APPROVAL_TRUST_CONTEXT_FILE", raising=False)
    with pytest.raises(ExternalSettlementError):
        preflight_external_settlement_approval(_native_payload(req, prepared, _receipt(req, prepared)))
    assert store.finalized_head()["height"] == -1


def test_real_native_preflight_verifies_signature_without_committing(monkeypatch, tmp_path):
    store, req, prepared = _seed(monkeypatch, tmp_path)
    _set_context(monkeypatch, tmp_path)
    claim = _receipt(req, prepared)
    result = preflight_external_settlement_approval(_native_payload(req, prepared, claim))
    assert result["approval_provenance_verified"] is True
    assert result["financial_execution_authorized"] is False
    assert result["atomic_nonce_consumption_verified"] is False
    assert result["quorum_finality_verified"] is False
    assert store.finalized_head()["height"] == -1
    assert not (store.root / "receipts" / "external-settlement").exists()
    # Repeated valid preflight is not nonce consumption or permission to finalize.
    repeated = preflight_external_settlement_approval(_native_payload(req, prepared, claim))
    assert repeated["receipt_sha256"] == result["receipt_sha256"]


def test_real_native_release_denied_even_with_valid_signature(monkeypatch, tmp_path):
    store, req, prepared = _seed(monkeypatch, tmp_path)
    _set_context(monkeypatch, tmp_path)
    authorized_preflight = _native_payload(req, prepared, _receipt(req, prepared))
    assert preflight_external_settlement_approval(authorized_preflight)["approval_provenance_verified"]
    # A prior arbitrary execution_hash was sufficient to reach finalization.
    authorized_preflight["execution_authorization"] = {
        "approval_id": req["approval_id"],
        "execution_hash": "fabricated-execution-hash",
        "target_payload_hash": prepared["finalization_payload"]["target_payload_hash"],
    }
    with pytest.raises(ExternalSettlementError, match="atomic_approval_consumption"):
        finalize_external_settlement(authorized_preflight)
    assert store.finalized_head()["height"] == -1


def test_wrong_amount_changes_canonical_signature_binding(monkeypatch, tmp_path):
    _, req, prepared = _seed(monkeypatch, tmp_path)
    _set_context(monkeypatch, tmp_path)
    original = _receipt(req, prepared)
    altered = {**req, "amount_minor": req["amount_minor"] + 1}
    # The candidate itself must be reconstructed; caller cannot swap amount.
    with pytest.raises(ExternalSettlementError):
        preflight_external_settlement_approval(_native_payload(altered, prepared, original))


def test_wrong_beneficiary_invalidates_native_candidate(monkeypatch, tmp_path):
    _, req, prepared = _seed(monkeypatch, tmp_path)
    _set_context(monkeypatch, tmp_path)
    changed = {**req, "user_id": "forged-beneficiary"}
    with pytest.raises(ExternalSettlementError):
        preflight_external_settlement_approval(_native_payload(changed, prepared, _receipt(req, prepared)))


def test_replayed_or_revoked_signer_rejected(monkeypatch, tmp_path):
    _, req, prepared = _seed(monkeypatch, tmp_path)
    _set_context(monkeypatch, tmp_path, revoked=["test-independent-founder-key-not-enrolled"])
    with pytest.raises(ExternalSettlementError):
        preflight_external_settlement_approval(_native_payload(req, prepared, _receipt(req, prepared)))


def test_unratified_or_empty_root_pins_fail_closed(monkeypatch, tmp_path):
    _set_context(monkeypatch, tmp_path, pins={**ROOT_PINS, "governance_sha256":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"})
    with pytest.raises(ApprovalPreflightError, match="root_pins"):
        load_trusted_context()


def test_insecure_permissions_on_trust_file_rejected(monkeypatch, tmp_path):
    path = _set_context(monkeypatch, tmp_path)
    os.chmod(path, 0o644)
    with pytest.raises(ApprovalPreflightError):
        load_trusted_context()


def test_symlinked_trust_file_rejected(monkeypatch, tmp_path):
    source = _set_context(monkeypatch, tmp_path)
    link = tmp_path / "untrusted_symlink.json"
    link.symlink_to(source)
    monkeypatch.setenv("WHALEZCHAIN_APPROVAL_TRUST_CONTEXT_FILE", str(link))
    with pytest.raises(ApprovalPreflightError, match="symlink"):
        load_trusted_context()


def test_expired_receipt_rejected(monkeypatch, tmp_path):
    _, req, prepared = _seed(monkeypatch, tmp_path)
    _set_context(monkeypatch, tmp_path)
    with pytest.raises(ExternalSettlementError):
        preflight_external_settlement_approval(_native_payload(
            req, prepared, _receipt(req, prepared, expiration=int(time.time())-1)
        ))


def test_replaced_signature_or_target_rejected(monkeypatch, tmp_path):
    _, req, prepared = _seed(monkeypatch, tmp_path)
    _set_context(monkeypatch, tmp_path)
    receipt = json.loads(_receipt(req, prepared))
    receipt["signature_hex"] = "0" * 128
    with pytest.raises(ExternalSettlementError):
        preflight_external_settlement_approval(_native_payload(req, prepared, json.dumps(receipt)))
    receipt = json.loads(_receipt(req, prepared))
    receipt["target_sha256"] = "f" * 64
    with pytest.raises(ExternalSettlementError):
        preflight_external_settlement_approval(_native_payload(req, prepared, json.dumps(receipt)))


def test_duplicate_json_keys_rejected(monkeypatch, tmp_path):
    _, req, prepared = _seed(monkeypatch, tmp_path)
    _set_context(monkeypatch, tmp_path)
    raw = _receipt(req, prepared)
    raw = raw[:-1] + ',"approval_id":"another"}'
    with pytest.raises(ExternalSettlementError):
        preflight_external_settlement_approval(_native_payload(req, prepared, raw))


def test_http_preflight_requires_internal_token_and_does_not_finalize(monkeypatch, tmp_path):
    store, req, prepared = _seed(monkeypatch, tmp_path)
    _set_context(monkeypatch, tmp_path)
    monkeypatch.setenv("WHALEZ_CHAIN_INTERNAL_TOKEN", "synthetic-private-test-token")
    client = TestClient(app)
    req_body = _native_payload(req, prepared, _receipt(req, prepared))
    assert client.post("/mainnet/settlement/approval-preflight", json=req_body).status_code == 401
    r = client.post(
        "/mainnet/settlement/approval-preflight",
        json=req_body, headers={"X-Whalez-Chain-Token": "synthetic-private-test-token"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["financial_execution_authorized"] is False
    assert store.finalized_head()["height"] == -1


def test_unconfigured_or_malformed_context_not_falsely_accepted(monkeypatch, tmp_path):
    path = _set_context(monkeypatch, tmp_path)
    path.write_text('{"schema":1,"schema":2}')
    os.chmod(path, 0o600)
    with pytest.raises(ApprovalPreflightError):
        load_trusted_context()