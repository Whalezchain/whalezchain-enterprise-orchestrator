"""
Sub‑domain manager for Whalez‑AI.

This module provides helper functions to generate sub‑domain names and matching
email aliases under a primary domain.  It is designed to be invoked by the
orchestrator when provisioning new modules or services.  Results are logged
to a file in the `logs/` directory for audit and playbook generation.
"""

import datetime
import json
from pathlib import Path
from typing import Iterable, Dict


def generate_subdomains(primary_domain: str, services: Iterable[str]) -> Dict[str, Dict[str, str]]:
    """
    Given a primary domain (e.g. "whalezchain.com") and a list of service
    identifiers (e.g. ["ledger", "trading", "api"]) returns a dictionary
    mapping each service to its sub‑domain and email alias.  The email alias
    uses the pattern `<service>@<subdomain>` to provide a clear correspondence.

    For example:

    >>> generate_subdomains("example.com", ["api", "console"])
    {
        "api": {
            "subdomain": "api.example.com",
            "email": "api@api.example.com"
        },
        "console": {
            "subdomain": "console.example.com",
            "email": "console@console.example.com"
        }
    }

    The function writes a log entry for each sub‑domain it generates to
    `logs/subdomains.log` in JSON lines format.
    """
    results = {}
    log_path = Path(__file__).resolve().parent.parent.parent / "logs" / "subdomains.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        for service in services:
            sub = f"{service}.{primary_domain}"
            email = f"{service}@{sub}"
            entry = {
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "service": service,
                "subdomain": sub,
                "email": email,
            }
            results[service] = {"subdomain": sub, "email": email}
            log_file.write(json.dumps(entry) + "\n")
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate sub-domains and emails for Whalez‑AI services.")
    parser.add_argument("domain", help="Primary verified domain (e.g. whalezchain.com)")
    parser.add_argument("services", nargs="+", help="List of service identifiers (e.g. ledger trading api)")
    args = parser.parse_args()
    mapping = generate_subdomains(args.domain, args.services)
    print(json.dumps(mapping, indent=2))