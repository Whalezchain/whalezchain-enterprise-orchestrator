# WHZ Settlement Bond Read Contract v1

Status: implementation branch / fail-closed integration contract.

## Purpose

The WhalezChain Enterprise Orchestrator is the canonical source for WHZ settlement-bond state used by the private Founder Console settlement gateway.

The contract is read-only. It does not create a second bond ledger and it does not mutate economic state.

## Endpoint

`GET /mainnet/settlement/account/{account_id}/settlement-bond?required_whz={amount}`

Required headers:

- `X-WHALEZ-CHAIN-TOKEN`
- `X-WHALEZ-CORRELATION-ID`

The account identifier is a canonical WhalezChain economic account. The v1 settlement bond used by the external settlement attestation is the configured platform settlement account, not a DeltaAlpha public user identity.

## Response

A verified response contains:

- `status=VERIFIED`
- `bond_state_id`
- `account_id`
- `total_whz`
- `available_whz`
- `locked_whz`
- `reserved_whz`
- `required_whz`
- `policy_version`
- `economic_state_root`
- finalized block height/hash
- correlation identity
- observation timestamp

In v1, `reserved_whz` is an explicit read-contract alias of the canonical economic state's `whz_bond_locked`. No second reservation counter is introduced.

The requested `required_whz` must be positive and must not exceed the currently available WHZ bond capacity. A shortage returns a non-success response and the caller must remain fail-closed.

## Canonical settlement relationship

Founder Console performs the public-domain eligibility, governance, provider and payment controls. WhalezChain verifies the configured required WHZ against the canonical platform settlement bond and, during the existing `/prepare` -> `/finalize` path, commits the WHZ lock into canonical economic state.

The existing Mainnet external settlement attestation remains the native finality path:

DeltaAlpha -> Founder Console -> WhalezChain prepare -> authorized finalization -> canonical WhalezChain receipt -> Whalez-AI Core read model.

No public application receives direct write access to WhalezChain state.