# Development log for v1.1.0

Date: 2025‑11‑12

This log records the key development activities completed during the transition from v1.0.0 (genesis) to v1.1.0.

* **Infrastructure migration** – moved from Google Cloud Workload Identity to Microsoft Azure Workload Identity Federation. Implemented an Azure Kubernetes Service (AKS) cluster via Terraform and configured Entra ID federated credentials.
* **CI/CD update** – replaced GCP authentication steps with `azure/login` and `azure/aks-set-context` actions in the deploy workflow. Ensured the pipeline requests the OIDC token by setting `id-token: write` permissions.
* **Sub‑domain manager** – added a new module to the orchestrator that generates sub‑domains under the main verified domain along with matching email aliases. This module writes logs to `logs/subdomains.log` whenever it runs.
* **Versioning** – introduced `VERSION`, `PROJECT`, and `CHANGELOG.md` files to track releases and maintain a clear migration path.
* **Documentation** – updated `README.md` with project overview and instructions.

These notes serve as an audit trail for the changes incorporated into v1.1.0 and will inform future playbooks and enhancements.