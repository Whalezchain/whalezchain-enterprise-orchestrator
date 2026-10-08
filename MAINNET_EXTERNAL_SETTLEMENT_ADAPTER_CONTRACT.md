# WhalezChain Mainnet External Settlement Adapter Contract

Status: CONTRACT ONLY / MAINNET NOT LIVE

This contract defines the boundary required for a verified external fiat settlement event to enter the canonical WhalezChain Mainnet finalization path.

## Input

The private runtime sends a JSON object containing at least:

- correlation_id
- idempotency_key
- user_id
- jurisdiction
- settlement_asset: {type, symbol}
- amount_minor
- currency
- external_provider
- external_reference
- provider_transaction_id
- provider_event_id
- provider_domain
- settlement_required_whz

For the first controlled corridor:

- external_provider = paystack
- currency = NGN
- jurisdiction = NGA

## Required behavior

The adapter must:

1. Reject missing, malformed, unsupported, or non-final provider events.
2. Resolve the transaction against the canonical WhalezChain economic/state model.
3. Apply policy-controlled settlement_required_whz.
4. Lock WHZ against the cumulative economic state when the policy requires a bond.
5. Execute the canonical WhalezChain Mainnet transaction/state transition.
6. Finalize an authorized block through the canonical Mainnet finalization path.
7. Persist and verify the resulting state root and economic-state root.
8. Return a canonical receipt only after finality is verified.
9. Be idempotent for the same correlation_id and idempotency_key.
10. Fail closed on ambiguity, duplicate-conflict, state-root mismatch, signature failure, or persistence failure.

## Output

The runtime adapter must return:

{
  "finality": "FINALIZED",
  "canonical_receipt": {
    "correlation_id": "...",
    "idempotency_key": "...",
    "external_provider": "paystack",
    "external_reference": "...",
    "provider_transaction_id": "...",
    "provider_event_id": "...",
    "currency": "NGN",
    "amount_minor": 0,
    "settlement_required_whz": false,
    "whz_settlement": {},
    "block_height": 0,
    "block_hash": "...",
    "state_root": "...",
    "economic_state_root": "...",
    "receipt_hash": "..."
  }
}

The exact internal receipt schema must follow the canonical Mainnet receipt model already established by the WhalezChain implementation. This document defines only the external-settlement binding requirements and must not create a second ledger.

## Architectural boundary

- DeltaAlpha owns the customer-facing payment initiation experience.
- Paystack or another authorized provider supplies the regulated external payment rail.
- The private Whalez runtime owns identity, policy, governance, reconciliation and the call into WhalezChain.
- WhalezChain remains the canonical native economic/state/provenance/finality authority.
- External providers do not become the WhalezChain system of record.
- WhalezChain does not become a bank or payment processor merely by recording an attested external settlement.

## Current implementation gap

The Mainnet code currently exists in the founder's local WhalezChain working branch but has not yet been pushed to this GitHub repository. Therefore this contract is intentionally not executable and must remain a review branch until the canonical Mainnet implementation is published, regression-tested, and wired to this adapter.
