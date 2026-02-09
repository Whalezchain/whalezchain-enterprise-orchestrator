# Infrastructure

## Default (Sovereign Baseline)
The default execution surface for this project is **self-hosted, containerized runtime** using Docker.

## Deprecated: Azure execution surface
This repository previously included Azure AKS/ACR pre-wiring under `infra/terraform/envs/prod`.

As of the Sovereign Baseline (2026-02-09), Azure is **retired** for this ecosystem.
The Terraform configuration remains for historical reference only and must not be used unless explicitly re-approved under governance.

## Optional surfaces
AWS/GCP may be introduced later as optional execution surfaces, but are not the default.
