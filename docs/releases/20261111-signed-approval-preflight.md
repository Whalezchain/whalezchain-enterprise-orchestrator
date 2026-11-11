# WhalezChain signed Founder approval preflight — integration checkpoint (2026-11-11)

**Status: engineering review candidate; read-only approval verification. No production activation.**

## Provenance

- Baseline: draft PR #17 at `fc7080a74aab7b401944f3e6e17af8e4bca79b9b`,
  `https://github.com/Whalezchain/whalezchain-enterprise-orchestrator/pull/17`.
- Baseline CI: `https://github.com/Whalezchain/whalezchain-enterprise-orchestrator/actions/runs/42939973709`,
  140 passing tests, one known collection warning (source verified in job).
- Imported standalone verifier exactly from `_recovery_p0/20261111_approval_provenance/approval_provenance.py`,
  SHA-256 `9ae439878281bb11c35fd8c75cf46c151cf9b55165e33ce8fc55537c95e3fc81`.
  Its original isolated tests: 28 passed. Native integration adds separate tests; no original file overwritten.
- The entire baseline candidate and the dirty local native checkout were preserved.
- This checkpoint also reconciles the market collector lifecycle decision:
  **boot_sequencer is the sole canonical runtime supervisor; PM2 is historical.**
  The legacy market-history collector still needs a single-writer, governed migration.
  No PM2 operation or service restart is authorized by this document.

## Implementation

1. `mainnet/approval_provenance.py`: imported immutable Ed25519 verifier, with
   exact canonical execution-payload hash, chain ID, target, scope, independent
   signer ID/revocation, expiry and pinned ROOT policy fields.
2. `mainnet/approval_preflight.py`: loads an operator-owned and private
   (0600) trusted verification context, rejects symlinked/incomplete inputs,
   invalid or empty ROOT policy pins; reconstructs an exact settlement payload
   and verifies an independently signed Founder receipt.
3. `mainnet/external_settlement.py`: reconstructs the canonical candidate from
   local chain state, confirms the supplied block and finalization data are
   unchanged, then calls signed-approval verification.
4. `main.py`: internal-token-protected
   `POST /mainnet/settlement/approval-preflight`; this is **not a public DeltaAlpha API**.
5. **Native finalize remains closed:** `require_atomic_financial_release()`
   deliberately denies finalization even when an independent signature is valid.
   `WHALEZCHAIN_MAINNET_EXECUTION_ENABLED=true` by itself cannot bypass the
   missing approval-nonce-consumption and independent-finality protocol.
   In two pre-existing isolated state-transition tests, a local monkeypatch
   bypasses this *unconditionally closed* gate to preserve deterministic internal
   state-machine regressions. That bypass does not exist on the runtime API.

## Verified local results

- Targeted native preflight + external settlement: **17 passed**.
- Complete candidate mainnet orchestration tests: **154 passed, 1 existing warning**
  in approximately 17 seconds on Termux, covering both earlier 140 tests and
  14 new approval-preflight regressions.
- Checks include valid and invalid signed receipts, changed beneficiary/amount,
  expiry, revocation, unsigned/fabricated authorization, private trust-file
  permissions, duplicate JSON keys, altered candidate, authenticated HTTP
  preflight and **denial of all real financial state changes**.
- Tests use isolated throwaway genesis and explicit synthetic signer keys.
  They are security regressions, **not** independent validator or custody proofs.
- Evidence: `_recovery_p0/20261111_release_reconciliation/SIGNED_GATE_NATIVE_TESTS_20261111.log`
  and `SIGNED_GATE_FULL_CHAIN_TESTS_20261111.log`.

## Required production gates (do not infer acceptance)

- **ROOT governance**: actual ratified `GOVERNANCE.md`, `CHANGE_CONTROL.md`
  and effective genesis registry, signed/provenanced effective hashes. Public
  main currently returned empty governance documents; the local ROOT copy is
  not automatically effective policy.
- **ED01–ED07**: actual Founder decisions with canonical approvals, signatures
  and effective dates, custody responsibilities, issuer/bond/unlock rules.
- **Custody**: independent protected signer enrollment, revocation, rotation,
  no export of private keys, device/hardware-assisted recovery.
- **Atomic financial execution**: implement one crash-safe transaction that
  consumes approval nonce/idempotency, authorizes exact amount/beneficiary,
  writes canonical chain state and immutable receipt, with restart/replay tests.
- **Consensus**: independent validators, verified quorum signatures, equivocation
  detection, fault tests, unbiased finality and multi-machine persistence.
  CometBFT build was intentionally stopped unfinished, and no binary was verified.
- **Independent recovery**: encrypted backup to owner-controlled off-device
  destination, separate device decrypt/restore and checkpoint/ledger validation.
  Existing Restic/R2 status does not certify full restoration.
- **Bridge**: authenticated canonical bridge proofs, replay and settlement
  controls and provider availability. All missing paths remain blocked.
- **Economic activation**: production genesis, allocations, settlement, PTN/WHZ/
  PRN policy, treasury actions and holds remain blocked pending ALL gates.
- **Founder release approval**: explicit review of immutable revision, separate
  signer identity, production observation and rollback evidence. A draft PR
  or passing tests never constitute activation authority.

## Future migration note

Replace `require_atomic_financial_release()` **only after** an independently
reviewed atomic nonce/funds/receipt protocol and independent validator finality
are implemented and tested. Do not replace it with an environment-variable
override, model judgment or a claimed Founder role string.

This document contains no live credentials, private Founder details, actual
allocation figures, or assertions of completed mainnet certification.