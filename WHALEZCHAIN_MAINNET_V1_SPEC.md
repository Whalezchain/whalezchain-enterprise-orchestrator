# WHALEZCHAIN MAINNET V1
## Production Network Specification

Status: DESIGN / NOT YET MAINNET
Scope: Existing Whalezchain system only
Initial assets: WHZ, PTN, PRN

---

## 1. PURPOSE

Whalezchain Mainnet v1 is the production network layer for the
existing Whalezchain economic and ledger system.

The objective is to transition from the current internal testnet
execution model to a controlled production network without
redesigning the established asset model.

This specification does NOT introduce:

- real-estate assets
- additional asset classes
- new speculative tokens
- new economic instruments

Those remain outside Mainnet v1 scope.

---

## 2. CURRENT VERIFIED FOUNDATION

The current internal engine already provides:

- deterministic canonical JSON serialization
- SHA-256 transaction hashing
- deterministic state-root hashing
- persistent account state
- persistent transaction journal
- transaction receipts
- asset validation through ASSET_REGISTRY
- credit operation
- transfer operation
- before/after state roots
- explicit execution boundaries

The current engine is explicitly marked:

- mainnet: false
- real_funds: false
- settlement: false
- external_consensus_claim: false
- validator_finality_claim: false
- testnet_only: true

Therefore the current engine MUST NOT be represented as a
production mainnet.

---

## 3. MAINNET OBJECTIVE

Mainnet v1 must provide a canonical production state machine
whose state transitions are ordered, validated, persisted,
reproducible, and finalized by an explicit network consensus
mechanism.

Required flow:

TRANSACTION
    ->
VALIDATION
    ->
CANONICAL ORDERING
    ->
BLOCK CONSTRUCTION
    ->
CONSENSUS
    ->
FINALITY
    ->
STATE TRANSITION
    ->
STATE ROOT
    ->
RECEIPT

---

## 4. INITIAL ASSET SCOPE

Mainnet v1 initial asset universe:

- WHZ
- PTN
- PRN

The existing asset authority remains authoritative for the asset
definitions.

No new asset may silently appear in Mainnet v1.

Any later asset introduction must be an explicit future governance
change.

### 4.1 Canonical product identities

| Symbol | Product identity | Technical role class |
| --- | --- | --- |
| WHZ | Whalez-Mint | ecosystem_policy_unit |
| PTN | Plutonium | platform_trade_note |
| PRN | Plutoranium | platform_receipt_note |

The technical role class exists for implementation, governance,
and audit clarity. It does not replace the product identity.

The identity table does not create any market-price, liquidity,
custody, settlement, exchange-listing, or jurisdictional claim.

---

## 5. MAINNET COMPONENTS

### 5.1 Genesis

Mainnet genesis must define:

- network identity
- chain identifier
- genesis timestamp
- initial state
- initial asset registry snapshot
- initial governance/authority configuration
- initial validator configuration
- genesis state root
- genesis hash

Genesis must be deterministic and reproducible.

---

### 5.2 Transaction

Every production transaction must have:

- unique transaction identifier
- sender
- recipient where applicable
- asset
- amount
- nonce / replay protection
- timestamp or deterministic ordering field
- transaction type
- signature/authorization data
- transaction hash

A transaction must be rejected if it cannot be authenticated,
validated, or replay-protected.

---

### 5.3 Validation

Validation must verify at minimum:

- asset exists
- amount is valid
- sender is authorized
- sender has sufficient balance where required
- nonce is valid
- transaction is not already committed
- transaction signature/authorization is valid
- transaction satisfies current policy

Invalid transactions must never mutate canonical state.

---

### 5.4 Blocks

A canonical block must contain:

- chain identifier
- block height
- previous block hash
- timestamp
- ordered transactions
- transaction root
- resulting state root
- block proposer/validator identity
- consensus/finality evidence
- block hash

The chain must be append-only after finalization.

---

### 5.5 Consensus

Mainnet requires an explicit consensus/finality mechanism.

The final consensus design is NOT selected in this document.

It must be chosen and documented before mainnet activation.

The selected mechanism must define:

- validator identity
- validator admission/removal
- block proposal
- block validation
- agreement/finality
- faulty validator handling
- restart/recovery behavior
- network partition behavior
- quorum/finality rules

No public claim of validator finality may be made until this
mechanism is implemented and tested.

---

### 5.6 State Engine

The existing deterministic balance/state logic should be preserved
where technically sound and placed beneath the production block layer.

Canonical production state must be derived from finalized blocks,
not from an independently mutated database.

The database is persistence.

The blockchain state transition is authoritative.

---

### 5.7 Receipts

Every finalized transaction must produce a deterministic receipt
containing sufficient evidence to establish:

- transaction hash
- block height
- block hash
- state transition result
- resulting state root
- finalization status

---

### 5.8 Recovery

Mainnet must support recovery from:

- process failure
- node restart
- database corruption
- incomplete block write
- network interruption

Recovery must deterministically reconstruct canonical state.

---

## 6. TESTNET / MAINNET SEPARATION

The current internal testnet remains a validation environment.

Testnet data MUST NOT automatically become mainnet economic state.

Mainnet must have its own canonical genesis.

Testnet remains available for:

- transaction testing
- failure testing
- upgrade testing
- integration testing
- regression testing

---

## 7. PRODUCTION SAFETY RULE

The following testnet flags MUST NOT simply be changed from
false to true to create mainnet:

- mainnet
- real_funds
- settlement
- external_consensus_claim
- validator_finality_claim

Production capability must come from implementation, not from
renaming or flipping safety flags.

---

## 8. MAINNET READINESS GATES

### GATE 1 — Deterministic Genesis
PASS required.

### GATE 2 — Transaction Authentication
PASS required.

### GATE 3 — Replay Protection
PASS required.

### GATE 4 — Canonical Block Production
PASS required.

### GATE 5 — Consensus / Finality
PASS required.

### GATE 6 — Persistent State Recovery
PASS required.

### GATE 7 — Receipt Verification
PASS required.

### GATE 8 — Adversarial Testing
PASS required.

### GATE 9 — Operational Monitoring
PASS required.

### GATE 10 — Production Deployment
PASS required.

No mainnet activation before all mandatory gates pass.

---

## 9. INITIAL MAINNET STATE POLICY

Mainnet v1 must establish its own documented genesis state.

No testnet balance is treated as real economic value merely because
it exists in the testnet journal.

Genesis allocation must be explicitly defined, reproducible, and
cryptographically committed.

---

## 10. OUT OF SCOPE

The following are deliberately excluded from Mainnet v1:

- real-estate tokenization
- additional asset classes
- unverified financial products
- anonymous validator admission
- uncontrolled minting
- uncontrolled supply changes
- hidden administrative balances
- undocumented state mutation
- direct exposure of internal runtime topology

---

## 11. SUCCESS CONDITION

Whalezchain Mainnet v1 is ready only when an independent verifier
can reconstruct the canonical chain and state from genesis through
the latest finalized block and obtain matching:

- block hashes
- transaction hashes
- state roots
- receipts
- asset registry snapshot

---

## 12. CURRENT STATUS

CURRENTLY VERIFIED:

- Existing internal testnet ledger/state engine
- Deterministic transaction hashing
- Deterministic state-root hashing
- Persistent journal
- Persistent account state
- Existing asset authority
- Existing WHZ / PTN / PRN scope

NOT YET VERIFIED:

- Production block network
- Production consensus
- Validator finality
- Mainnet genesis
- Mainnet peer/network layer
- Production replay protection
- Production recovery protocol
- Production adversarial test suite

Therefore:

MAINNET STATUS = NOT READY FOR ACTIVATION

NEXT ENGINEERING TARGET =
Production network layer around the existing ledger/state foundation.
