# Sub-domain naming conventions

This document describes general naming rules for Whalez‑AI service namespaces.

1. **Primary domain** – production sub-domains are rooted under an approved primary domain.
2. **Service identifier** – each public-facing service uses a short, lower-case identifier. Avoid spaces or special characters.
3. **Sub-domain** – constructed as `<service>.<primary>`.
4. **Email alias** – service-specific aliases may follow the same identifier convention where enabled.
5. **Uniqueness** – deployments must check existing names before provisioning a new namespace. Numeric suffixes may be used to avoid collisions.
6. **Auditability** – namespace creation and changes should be recorded by the deployment environment.

Implementation-specific infrastructure, private control surfaces, approval chains, and internal service names are intentionally excluded from this public repository.
