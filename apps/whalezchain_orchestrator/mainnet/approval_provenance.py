"""Public verification of exact-operation approval receipts.

Caller must supply independently enrolled signer and effective policy pins.
Verification does not reserve a nonce, commit money, or grant release approval.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

DOMAIN = b'WHALEZ/FOUNDER-APPROVAL-RECEIPT/V1\x00'
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
BODY_FIELDS = frozenset({
    'schema', 'approval_id', 'approved_by', 'authority', 'decision', 'scope',
    'chain_id', 'execution_payload_sha256', 'target_sha256', 'root_pins',
    'signer_key_id', 'nonce_sha256', 'issued_at', 'expires_at',
})
PIN_FIELDS = frozenset({'governance_sha256', 'change_control_sha256', 'genesis_registry_sha256'})


class ApprovalProvenanceError(ValueError):
    pass


def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def signing_bytes(body):
    _validate_body(body)
    return DOMAIN + canonical_json(body)


def parse_signed_receipt(raw):
    if type(raw) is not str or len(raw) > 16384:
        raise ApprovalProvenanceError('invalid_receipt_json')
    def pairs(items):
        output = {}
        for key, value in items:
            if key in output:
                raise ApprovalProvenanceError('duplicate_json_key')
            output[key] = value
        return output
    def reject_constant(value):
        raise ApprovalProvenanceError('nonfinite_json')
    try:
        receipt = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject_constant)
    except (ValueError, TypeError) as exc:
        raise ApprovalProvenanceError('invalid_receipt_json') from exc
    if type(receipt) is not dict or set(receipt) != BODY_FIELDS | {'signature_hex'}:
        raise ApprovalProvenanceError('invalid_receipt_fields')
    return receipt


def _hex(value):
    return type(value) is str and HEX64.fullmatch(value) is not None


def _pins(pins):
    return (type(pins) is dict and set(pins) == PIN_FIELDS and
            all(_hex(value) for value in pins.values()))


def _validate_body(body):
    if type(body) is not dict or set(body) != BODY_FIELDS:
        raise ApprovalProvenanceError('invalid_receipt_fields')
    if (body['schema'] != 'whalez.founder.approval.receipt.v1' or
            body['approved_by'] != 'FOUNDER' or body['authority'] != 'FOUNDER_CONSOLE' or
            body['decision'] != 'approved'):
        raise ApprovalProvenanceError('invalid_receipt_context')
    for key in ('approval_id', 'scope', 'chain_id', 'signer_key_id'):
        if type(body[key]) is not str or not 1 <= len(body[key]) <= 160:
            raise ApprovalProvenanceError('invalid_' + key)
    for key in ('execution_payload_sha256', 'target_sha256', 'nonce_sha256'):
        if not _hex(body[key]):
            raise ApprovalProvenanceError('invalid_' + key)
    if not _pins(body['root_pins']):
        raise ApprovalProvenanceError('invalid_root_pins')
    start, end = body['issued_at'], body['expires_at']
    if (type(start) is not int or type(end) is not int or
            not 0 < start < end <= start + 300):
        raise ApprovalProvenanceError('invalid_receipt_lifetime')


def verify_receipt(receipt, *, enrolled_public_key_hex, enrolled_key_id,
                   expected_approval_id, execution_payload, expected_chain_id,
                   effective_root_pins, revoked_key_ids, now):
    """Verify a receipt against trusted enrollment/context, with no side effects."""
    if type(receipt) is not dict or set(receipt) != BODY_FIELDS | {'signature_hex'}:
        raise ApprovalProvenanceError('invalid_receipt_fields')
    body = {key: value for key, value in receipt.items() if key != 'signature_hex'}
    payload = signing_bytes(body)
    if (not _hex(enrolled_public_key_hex) or not _pins(effective_root_pins) or
            type(revoked_key_ids) is not frozenset or type(now) is not int or
            type(execution_payload) is not dict or not execution_payload or
            type(enrolled_key_id) is not str or not enrolled_key_id):
        raise ApprovalProvenanceError('invalid_trusted_context')
    if enrolled_key_id in revoked_key_ids:
        raise ApprovalProvenanceError('revoked_signer')
    if now < body['issued_at'] - 30 or now >= body['expires_at']:
        raise ApprovalProvenanceError('expired_or_not_yet_valid')
    expected = {
        'approval_id': expected_approval_id, 'signer_key_id': enrolled_key_id,
        'chain_id': expected_chain_id, 'root_pins': effective_root_pins,
        'scope': execution_payload.get('scope'),
        'target_sha256': execution_payload.get('target_sha256'),
        'execution_payload_sha256': hashlib.sha256(canonical_json(execution_payload)).hexdigest(),
    }
    if any(body[key] != value for key, value in expected.items()):
        raise ApprovalProvenanceError('receipt_execution_or_policy_mismatch')
    signature = receipt['signature_hex']
    if type(signature) is not str or re.fullmatch(r'[0-9a-f]{128}', signature) is None:
        raise ApprovalProvenanceError('invalid_receipt_signature_encoding')
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(enrolled_public_key_hex)).verify(
            bytes.fromhex(signature), payload)
    except (InvalidSignature, ValueError) as exc:
        raise ApprovalProvenanceError('invalid_receipt_signature') from exc
    return {'receipt_signature_verified': True,
            'receipt_sha256': hashlib.sha256(canonical_json(receipt)).hexdigest(),
            'approval_id': body['approval_id'], 'nonce_sha256': body['nonce_sha256'],
            'execution_payload_sha256': body['execution_payload_sha256'],
            'financial_execution_authorized': False}