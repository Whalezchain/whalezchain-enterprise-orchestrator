# Whalezchain Enterprise Orchestrator

Official enterprise edition v1.0.0 (first public baseline).

This repository contains the **complete source tree** for the Whalez‑AI Sovereign Finance OS.  
It combines the original genesis release (v1.0.0) with all subsequent upgrades, including the
finance‑core modules, the Azure migration and the sub‑domain orchestration.  Each new
version is delivered as a full snapshot of the project rather than a partial patch.

## Project overview

Whalez‑AI is a self‑sovereign orchestration platform for financial ecosystems. It includes:

* **Public apps** – consumer‑facing exchange and trade portals (e.g. `whalezchain-web`, `deltaalpha-tradepro`).
* **Private apps** – operational consoles for founders and operators (`founder-console`, `workbench`).
* **Core services** – orchestrator, funded ledger, treasury, realtime bus, identity service, connector, receipts, etc.
* **Infrastructure code** – Helm charts, Terraform modules, continuous delivery pipelines.
* **Sub‑domain manager** – generates sub‑domains and email addresses under a primary domain to support modular deployments.

## Getting started

1. Review `VERSION` and `CHANGELOG.md` to understand the evolution of the project.
2. Configure your Azure subscription, Entra ID (formerly Azure AD) and GitHub secrets as described in `infra/terraform/envs/prod/variables.tf` and `.github/workflows/deploy.yml`.
3. Run the Terraform in `infra/terraform/envs/prod` to provision the AKS cluster and identity components.
4. Push a tagged release to trigger the deployment workflow.

## Sub‑domain orchestration

The orchestrator now includes a `subdomain_manager.py` module under `services/orchestrator/`.  
This helper can generate consistent sub‑domains and corresponding email aliases for new modules.  
See `subdomain_rules.md` for naming conventions.

### New in v1.2.1

This build introduces two important scaffolding layers:

- **Identity & Genesis** – the `identity/` folder contains an orb manifest and a conceptual
  founder genesis wallet spec. These define *who* Whalez‑AI is meant to be (sovereign AI firm),
  without embedding any live keys.
- **AKS environment config** – `infra/terraform/envs/prod/env.prod.json` is a template that
  centralises Azure subscription / tenant / cluster identifiers. Terraform reads from this file
  so the same code can be replayed safely across environments.
