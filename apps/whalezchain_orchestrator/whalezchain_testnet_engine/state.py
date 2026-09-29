from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_TERMUX_RUNTIME_ROOT = (
    Path("/data/data/com.termux/files/home/whalez/runtime")
    / "whalezchain-testnet-engine"
    / "state"
)


def _runtime_root() -> Path:
    configured = os.environ.get("WHALEZ_RUNTIME_ROOT")

    if configured:
        return Path(configured).expanduser().resolve() / "state"

    if DEFAULT_TERMUX_RUNTIME_ROOT.exists():
        return DEFAULT_TERMUX_RUNTIME_ROOT

    return (
        Path.home()
        / "whalez"
        / "runtime"
        / "whalezchain-testnet-engine"
        / "state"
    )


RUNTIME_ROOT = _runtime_root()
RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)

ACCOUNTS_FILE = RUNTIME_ROOT / "accounts.json"
JOURNAL_FILE = RUNTIME_ROOT / "journal.jsonl"
METADATA_FILE = RUNTIME_ROOT / "metadata.json"
STATE_ROOT_FILE = RUNTIME_ROOT / "state_root.txt"


def load_accounts() -> Dict[str, Dict[str, str]]:
    if not ACCOUNTS_FILE.exists():
        return {}

    return json.loads(ACCOUNTS_FILE.read_text())


def save_accounts(accounts: Dict[str, Dict[str, str]]) -> None:
    ACCOUNTS_FILE.write_text(
        json.dumps(accounts, indent=2, sort_keys=True) + "\n"
    )


def load_journal() -> List[Dict[str, Any]]:
    if not JOURNAL_FILE.exists():
        return []

    rows = []

    for line in JOURNAL_FILE.read_text().splitlines():
        line = line.strip()

        if not line:
            continue

        rows.append(json.loads(line))

    return rows


def append_journal(entry: Dict[str, Any]) -> None:
    with JOURNAL_FILE.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True))
        f.write("\n")


def save_metadata(metadata: Dict[str, Any]) -> None:
    METADATA_FILE.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    )


def load_metadata() -> Dict[str, Any]:
    if not METADATA_FILE.exists():
        return {}

    return json.loads(METADATA_FILE.read_text())


def save_state_root(state_root: str) -> None:
    STATE_ROOT_FILE.write_text(state_root + "\n")


def load_state_root() -> str:
    if not STATE_ROOT_FILE.exists():
        return ""

    return STATE_ROOT_FILE.read_text().strip()
