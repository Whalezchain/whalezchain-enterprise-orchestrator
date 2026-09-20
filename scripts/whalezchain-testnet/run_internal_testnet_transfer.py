#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from whalezchain_orchestrator.whalezchain_testnet_engine.runtime import engine


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a real internal Whalezchain testnet balance mutation."
    )
    parser.add_argument("--runtime-root", default="~/whalez/runtime/whalezchain-testnet-engine")
    parser.add_argument("--credit-amount", default="10.00000000")
    parser.add_argument("--transfer-amount", default="1.00000000")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.runtime_root).expanduser() / stamp

    founder = "whalezchain-testnet://founder/internal-alpha"
    validator = "whalezchain-testnet://validator/internal-beta"


    credits = []
    transfers = []

    for symbol in ["PTN", "PRN", "WHZ"]:
        credits.append(
            engine.credit(
                founder,
                symbol,
                args.credit_amount,
                "internal testnet faucet credit",
            )
        )

    for symbol in ["PTN", "PRN", "WHZ"]:
        transfers.append(
            engine.transfer(
                founder,
                validator,
                symbol,
                args.transfer_amount,
            )
        )

    final_state = engine.state()
    receipt = engine.receipt()

    milestone = {
        "stamp": stamp,
        "milestone_type": "canonical_whalezchain_internal_testnet_balance_engine_transfer",
        "network_class": "internal_whalezchain_testnet",
        "accounts": [founder, validator],
        "assets": ["PTN", "PRN", "WHZ"],
        "credit_amount_per_asset": args.credit_amount,
        "transfer_amount_per_asset": args.transfer_amount,
        "state_root": receipt["state_root"],
        "receipt_hash": receipt["receipt_hash"],
        "journal_count": receipt["journal_count"],
        "boundaries": receipt["boundaries"],
    }

    write_json(out_dir / "credits.json", credits)
    write_json(out_dir / "transfers.json", transfers)
    write_json(out_dir / "state.json", final_state)
    write_json(out_dir / "receipt.json", receipt)
    write_json(out_dir / "milestone-006.json", milestone)

    print("== WHALEZCHAIN INTERNAL TESTNET TRANSFER COMPLETE ==")
    print(f"runtime_dir={out_dir}")
    print(f"state_root={receipt['state_root']}")
    print(f"receipt_hash={receipt['receipt_hash']}")
    print("credit_amount_per_asset=" + args.credit_amount)
    print("transfer_amount_per_asset=" + args.transfer_amount)
    print("journal_count=" + str(receipt["journal_count"]))
    print("No mainnet used.")
    print("No real funds used.")
    print("No custody performed.")
    print("No trading performed.")
    print("No settlement performed.")
    print("No authority changed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
