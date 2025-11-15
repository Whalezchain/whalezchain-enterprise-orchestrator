# Changelog

## v1.2.1 – Identity & AKS env scaffold

- Added Whalez-AI orb manifest describing sovereign AI org and governance key.
- Added founder genesis wallet spec (documentation only, no live keys).
- Added env.prod.json template to drive Azure AKS Terraform deployment.
- Updated README version banner to v1.2.1.


## v1.2.0 – Azure pre‑wire integration and full package rebuild (2025‑11‑12)

* **Full package rebuild.**  This release bundles the entire Whalez‑AI source tree again to ensure that all
  prior features, services and infrastructure are included alongside the new capabilities.  It
  supersedes v1.1.0 by incorporating every file from the genesis release, the finance‑core modules,
  and the Azure migration into a single coherent tree.  Future versions will follow this practice
  so that upgrades are always delivered as complete snapshots rather than partial patches.
* **Azure pre‑wired infrastructure.**  The Terraform configuration under
  `infra/terraform/envs/prod` has been updated to fully provision an Azure Kubernetes Service (AKS)
  cluster and to set up Microsoft Entra (Azure AD) workload identity federation for GitHub Actions.
  The associated GitHub workflow `deploy.yml` now uses `azure/login@v2` and
  `azure/aks-set-context@v3` to authenticate and deploy Helm charts to AKS using the OIDC token from
  GitHub【284444970615389†L287-L291】【445045298118697†L55-L63】.
* **Deployment pipelines.**  Added a `.github` directory with workflow files for CI, security
  scanning, SBOM generation/signing and Azure deployment.  These workflows are ready to use with
  GitHub Secrets and Workload Identity Federation and will build, test and deploy the project on
  every release.
* **Sub‑domain automation enhancements.**  The orchestrator’s `subdomain_manager.py` continues to
  generate sub‑domain names and email aliases.  This release clarifies how new sub‑domains should
  be named under the primary domain and ensures the naming rules are auditable.  The
  `subdomain_rules.md` file documents the conventions.
* **Development logs and receipts.**  A new development log file `logs/update_v1.2.0.md` records
  the activities performed during this release: merging of previous seeds into a single tree,
  integration of the Azure pre‑wired configuration, creation of workflow files and update of
  version metadata.  These logs serve as provenance for future playbook generation.


## v1.1.0 – Azure migration and sub‑domain orchestration (2025‑11‑12)

* Migrated infrastructure code from Google Cloud to **Microsoft Azure** using the `azurerm` and `azuread` providers.
  * Added an AKS cluster with `oidc_issuer_enabled` and `workload_identity_enabled`.
  * Created an Entra ID application and service principal, and configured a federated identity credential to trust tokens from GitHub OIDC【284444970615389†L287-L291】【445045298118697†L55-L63】.
  * Assigned contributor permissions on the AKS cluster to the service principal.
* Updated the GitHub Actions deployment workflow to authenticate via `azure/login@v2` and set AKS context with `azure/aks-set-context@v3`.  
  The workflow now uses Workload Identity Federation and no longer depends on static secrets【288502149926624†L71-L83】.
* Added `services/orchestrator/subdomain_manager.py` and `subdomain_rules.md` to generate sub‑domains and matching email addresses under a primary domain.
* Added a `logs/update_v1.1.0.md` file to record the development activities for this release.
* Introduced `VERSION` and `PROJECT` files for metadata.

## v1.0.0 – Genesis release

* Initial release of Whalez‑AI Sovereign Finance OS (genesis).  
  Included core services (funded ledger, treasury, realtime bus), playbooks, identity assets, public and private apps, CI/CD pipelines, and a GitHub–GCP deployment workflow.
* This version laid the groundwork for a self‑sovereign, audit‑driven orchestration platform.
## v1.0.0-enterprise – First official Whalezchain Enterprise Orchestrator release (2025-11-12)

- Rebranded the codebase from internal Whalez-AI development snapshots into the first official
  **Whalezchain Enterprise Orchestrator** release.
- Preserved previous development history and logs while standardizing naming, structure,
  and CI/CD pipelines for production use.
- Marked this version as the canonical baseline for future migrations and upgrades.
