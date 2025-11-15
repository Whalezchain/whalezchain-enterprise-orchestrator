# Sub‑domain naming conventions

This document describes the rules used by Whalez‑AI to generate sub‑domains and
associated email aliases.  These conventions ensure consistency across the
platform and allow the orchestrator to autonomously create new namespaces
under the primary domain.

1. **Primary domain** – all sub‑domains are rooted under a single, verified
   domain used by the public exchange and app (e.g. `whalezchain.com`).
2. **Service identifier** – each functional unit (e.g. `ledger`, `trading`,
   `api`, `console`, `foundation`) is represented by a short, lower‑case
   string.  Avoid spaces or special characters.
3. **Sub‑domain** – constructed by concatenating the service identifier and
   primary domain with a dot: `<service>.<primary>`.  For example,
   `ledger.whalezchain.com`.
4. **Email alias** – each sub‑domain has a corresponding catch‑all email in
   the form `<service>@<subdomain>`.  For example, `ledger@ledger.whalezchain.com`.
5. **Uniqueness** – the orchestrator checks existing sub‑domains to avoid
   collisions.  If a collision is detected, it appends a numeric suffix
   (e.g. `api2.whalezchain.com`).
6. **Audit log** – every generated sub‑domain and email alias is recorded in
   `logs/subdomains.log` with a timestamp and service name.  This audit log
   can be used to produce playbooks and to verify naming history.

By automating sub‑domain and email creation, the orchestrator can quickly
provision new modules without manual DNS or identity configuration.  See
`services/orchestrator/subdomain_manager.py` for implementation details.

> Note: In the enterprise edition, sub-domains and email aliases are requested by the Whalezchain Enterprise Orchestrator and approved or rejected via the Founder Console.
