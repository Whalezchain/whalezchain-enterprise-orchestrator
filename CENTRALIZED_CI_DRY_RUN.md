# Centralized GitHub Actions dry-run

This candidate centralizes repeatable workflow logic while each caller checks out and tests its own repository at the caller event SHA. Every external action and reusable workflow reference is pinned to a full commit SHA. Caller jobs grant only the permissions required by that category; no secrets are passed or inherited.

The pilot uses the public Whalezchain/whalezchain-enterprise-orchestrator repository as a temporary workflow provider because GitHub reports its reusables can be called publicly. This repository also contains financial infrastructure, so it is not the recommended permanent host. The existing private deltaalpha-trade-pro/whalez-ci repository reports reusable-workflow access none; GitHub private workflow sharing does not cross the user's account/Whalezchain organization boundary. Do not change its visibility or access settings.

For controlled adoption, move generic reusable workflows into a dedicated CI-only provider with no financial code or production secrets. It must be publicly accessible to both public callers and private callers that are explicitly allowed to use public reusable workflows, or be split into correctly scoped providers. Caller repositories remain the execution and billing context. Each caller keeps its own repository-specific tests and can continue running them locally if the provider is unavailable.

## Candidate categories

- Python validation with repository-specific install/test commands and a caller checkout/SHA assertion.
- Node/Next validation using the caller's lockfile and build/test commands.
- Trivy filesystem security scanning at the verified 0.35.0 commit and CodeQL v3 at a reviewed full SHA.
- Governance-policy static checks for pinned references, explicit job permissions, and forbidden PR/secret/deployment patterns.
- CycloneDX SBOM and non-production evidence artifacts with seven-day retention.
- WhalezChain settlement/API/economic-root/persistence tests with mainnet execution explicitly disabled.
- API contract tests with local/no-external-network intent and caller-specific test commands.
- Non-production release verification manifest only; it does not deploy, sign, release, or publish assets.

## Security boundaries

- No secrets input, secrets: inherit, deployment environment, or write-capable code checkout token.
- pull_request, push-to-pilot-branch, and manual test triggers only; no pull_request_target.
- Checkout explicitly names github.repository and github.sha, then asserts git rev-parse HEAD == GITHUB_SHA.
- Test and build commands run with contents: read and no secrets.
- CodeQL and Trivy run with contents: read only. CodeQL SARIF and Trivy SARIF are retained as seven-day artifacts; CodeQL does not upload into code scanning, which avoids collision with repositories using default CodeQL setup. A repository that wants code-scanning publication must separately adopt and validate advanced setup with the required permission.
- SBOM and execution evidence are non-production artifacts; no signing identity or deployment permission is present.

## Pilot workflow references

The caller workflows are added only after the provider workflow commit is pushed; their uses refs then pin that exact immutable SHA. CI runs are expected to report provider and caller repository/SHA in step summaries.
