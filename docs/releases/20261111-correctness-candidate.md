# Conservation and recovery release candidate — 2026-11-11

This candidate builds on PR #15 at 4fd77fdeb725e7eb007d08fe478f8669ab93c780. It retains its conservation regressions and reconciles local canonical nonce enforcement, replay/recovery integrity repairs and genesis-committed PRN issuance policy propagation.

Source review covered the starting-state trust boundary, nonce continuity, missing/gapped/duplicate history, persisted transaction authentication, metadata publication crashes, competing writers, historical root mismatch rejection and reopening with a PRN supply cap. The complete candidate orchestrator suite passed 140 tests on Termux, with one existing Pydantic model collection warning. CI is configured to check out the exact pull-request head and run the complete suite. Remote CI results and independent human review must be checked on the resulting immutable SHA.

The release is an engineering candidate. It does not activate mainnet, enroll signers, select economic policies, ratify ROOT, run external settlement or establish independent validator operation. The native ED04 denominator change, bridge/runtime modifications and uncompiled Android companion are deliberately excluded from this correctness revision pending their separate acceptance. Existing local native sources are preserved.

Recovery rejects incompatible finalized history rather than rewriting block or state hashes. The existing finalized marker is not cryptographic quorum proof. A missing genesis PRN policy disables minting; this candidate does not assign production issuers or a cap.

Production approval, financial hold release and activation remain separate decisions after consensus, custody, signed receipt provenance, atomic financial recovery and independent restore acceptance.
