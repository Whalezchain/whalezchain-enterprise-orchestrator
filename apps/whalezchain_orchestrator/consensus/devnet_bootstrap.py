"""Provision one isolated four-validator CometBFT laboratory network.

Not production infrastructure. All keys and chain state remain in a 0700
review directory; never commit the generated files or reuse devnet keys.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import subprocess

from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore
from whalezchain_orchestrator.mainnet.genesis import GenesisValidator, build_genesis
from whalezchain_orchestrator.mainnet.genesis_economic_state import initialize_genesis_economic_state
from whalezchain_orchestrator.tests.mainnet_test_helpers import account


NETWORK = "whalezchain-internal-devnet-20261123"
NODES = 4


def _edit_config(path: Path, peer_addresses: list[str], index: int) -> None:
    original = path.read_text()
    section = ""
    modified: list[str] = []
    matched: set[str] = set()
    settings = {
        ("", "proxy_app"): f'"tcp://127.0.0.1:{26658 + 10 * index}"',
        ("rpc", "laddr"): f'"tcp://127.0.0.1:{26657 + 10 * index}"',
        ("p2p", "laddr"): f'"tcp://127.0.0.1:{26656 + 10 * index}"',
        ("p2p", "persistent_peers"): '"' + ",".join(
            peer for j, peer in enumerate(peer_addresses) if j != index
        ) + '"',
        ("p2p", "addr_book_strict"): "false",
        ("p2p", "allow_duplicate_ip"): "true",
        ("p2p", "pex"): "false",
        ("consensus", "timeout_commit"): '"1s"',
    }
    for line in original.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped.strip("[]").strip()
        if "=" in line and not stripped.startswith("#"):
            name = line.split("=", 1)[0].strip()
            key = (section, name)
            if key in settings:
                modified.append(f"{name} = {settings[key]}")
                matched.add(key)
                continue
        modified.append(line)
    missing = set(settings) - matched
    if missing:
        raise ValueError(f"unexpected CometBFT configuration: missing {sorted(missing)}")
    path.write_text("\n".join(modified) + "\n")


def provision(binary: Path, directory: Path) -> dict:
    os.umask(0o077)
    if directory.exists() or directory.is_symlink():
        raise ValueError("refusing to overwrite any prior devnet or private keys")
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(mode=0o700)
    subprocess.run(
        [str(binary), "testnet", "--v", str(NODES),
         "--o", str(directory), "--populate-persistent-peers=false"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    nodes = [directory / f"node{i}" for i in range(NODES)]
    for node in nodes:
        if not (node / "config" / "genesis.json").is_file():
            raise ValueError("CometBFT did not generate complete node files")
    comet_genesis = json.loads((nodes[0] / "config" / "genesis.json").read_text())
    validator_config = tuple(
        GenesisValidator(
            validator_id=f"devnet-validator-{idx}",
            public_key=base64.b64decode(raw["pub_key"]["value"], validate=True).hex(),
        )
        for idx, raw in enumerate(comet_genesis["validators"])
    )
    if len(validator_config) != NODES:
        raise ValueError("validator count must be four")
    economic_state = initialize_genesis_economic_state(
        ptn_genesis_supply="1000.00000000"
    )
    genesis = build_genesis(
        genesis_timestamp="2026-11-23T04:30:00Z",
        initial_state={account("alice"): {
            "PTN": "10.00000000", "PRN": "0.00000000", "WHZ": "0.00000000",
        }},
        validators=validator_config,
        authority_config={"mode": "test", "prn_issuance_policy": {
            "authorized_issuers": [], "max_supply": "1.00000000",
        }},
        economic_state=economic_state,
    )
    addresses: list[str] = []
    for idx, node in enumerate(nodes):
        node_id = subprocess.run(
            [str(binary), "--home", str(node), "show-node-id"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if not node_id or len(node_id) != 40:
            raise ValueError("cannot verify generated Comet node public ID")
        addresses.append(f"{node_id}@127.0.0.1:{26656 + 10 * idx}")
    for index, node in enumerate(nodes):
        os.chmod(node, 0o700)
        for key in (node / "config").glob("*priv*"):
            os.chmod(key, 0o600)
        for key in (node / "config").glob("*key.json"):
            os.chmod(key, 0o600)
        whalez_root = node / "whalez-state"
        MainnetChainStore(whalez_root).initialize_genesis(genesis)
        existing = json.loads((node / "config" / "genesis.json").read_text())
        existing["chain_id"] = NETWORK
        existing["app_state"] = {"whalez_genesis_hash": genesis.genesis_hash}
        (node / "config" / "genesis.json").write_text(
            json.dumps(existing, sort_keys=True, indent=2) + "\n"
        )
        _edit_config(node / "config" / "config.toml", addresses, index)
        (node / "backend").mkdir(mode=0o700)
    result = {
        "network_chain_id": NETWORK,
        "whalez_genesis_hash": genesis.genesis_hash,
        "nodes": NODES,
        "validator_pubkeys": [v.public_key for v in validator_config],
        "p2p_ports": [26656 + 10 * i for i in range(NODES)],
        "rpc_ports": [26657 + 10 * i for i in range(NODES)],
        "abci_ports": [26658 + 10 * i for i in range(NODES)],
        "real_funds": False,
        "production_mainnet": False,
    }
    (directory / "devnet_manifest.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comet-binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = provision(args.comet_binary, args.output)
    print(json.dumps({
        "network_chain_id": result["network_chain_id"],
        "whalez_genesis_hash": result["whalez_genesis_hash"],
        "nodes": result["nodes"],
        "production_mainnet": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
