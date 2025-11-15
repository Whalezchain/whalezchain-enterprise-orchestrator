# Founder / Genesis wallet spec (design doc)

This file explains the rules for the Whalez‑AI "genesis event". It does **not**
contain real keys, only protocol.

## Roles

- **Founder wallet** – personal authority of Alpha‑Whalez (used rarely).
- **Treasury wallet** – main reserve backing operations, salaries, and R&D.
- **Ledger wallet(s)** – hot / warm wallets used for day‑to‑day platform flows.

## One‑time genesis event

1. A dedicated hardwallet is initialised completely offline.
2. It derives the three wallets above from a single seed.
3. The mapping from seed → (founder, treasury, ledger) is written down on paper
   and stored in multiple secure physical locations.
4. From that moment on:
   - no new wallets are derived from that seed;
   - the seed is never typed into any online device;
   - all online systems only ever see public keys / addresses.

## How the orchestrator should treat this

- The repo only stores *placeholders* like `FOUNDER_WALLET_ADDRESS` in configs.
- Any script that needs to fund infrastructure (e.g. paying for cloud costs
  from block rewards) should:
  - read configurable addresses from a `.env` or JSON file; and
  - never assume it can see or reconstruct the underlying seed.

This way the **idea** of the genesis is encoded in code and docs,
while the actual money keys stay air‑gapped with the human founder.
