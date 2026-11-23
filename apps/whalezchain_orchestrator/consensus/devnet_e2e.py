"""Real, bounded four-validator CometBFT + WhalezChain ABCI integration test.

This runs ONLY inside an isolated local devnet, with synthetic assets and
temporary node keys. It never touches production stores, real wallets or
external networks. Every child process is terminated before return.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from whalezchain_orchestrator.consensus.devnet_bootstrap import NETWORK
from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore
from whalezchain_orchestrator.mainnet.cometbft_state_machine import _app_hash
from whalezchain_orchestrator.mainnet.transaction import canonical_json
from whalezchain_orchestrator.tests.mainnet_test_helpers import (
    account, signed_mainnet_transaction,
)


def _rpc(port: int, action: str, timeout: float = 2.0) -> dict:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/{action}", timeout=timeout
    ) as response:
        value = json.load(response)
    if value.get("error"):
        raise ValueError(f"Comet RPC {port}/{action} returned an error")
    return value["result"]


def _height(node: int) -> int:
    return int(_rpc(26657 + node * 10, "status")["sync_info"]["latest_block_height"])


def _await_height(nodes: list[int], minimum: int, timeout: float) -> dict[int, int]:
    deadline = time.monotonic() + timeout
    last: dict[int, int] = {}
    while time.monotonic() < deadline:
        for i in nodes:
            try:
                last[i] = _height(i)
            except (OSError, ValueError, KeyError, TimeoutError):
                last[i] = -1
        if all(last.get(i, -1) >= minimum for i in nodes):
            return last
        time.sleep(0.8)
    raise RuntimeError(f"validator height check failed; observed {last}, target {minimum}")


def _start(cmd: list[str], env: dict, log_path: Path, children: list) -> None:
    handle = log_path.open("wb")
    process = subprocess.Popen(
        cmd, stdout=handle, stderr=subprocess.STDOUT,
        env=env, start_new_session=True,
    )
    children.append((process, handle, log_path))


def _stop(children: list) -> None:
    for process, _, _ in reversed(children):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for process, _, _ in reversed(children):
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)
    for _, handle, _ in children:
        handle.close()


def _heads(network: Path) -> dict[int, dict]:
    result = {}
    for i in range(4):
        store = MainnetChainStore(network / f"node{i}" / "whalez-state")
        verified = store.verified_snapshot()
        state = verified["state"]
        result[i] = {
            "height": int(verified["height"]),
            "block_hash": str(verified["block_hash"]),
            "state_root": str(verified["state_root"]),
            "alice_ptn": state[account("alice")]["PTN"],
            "bob_ptn": state.get(account("bob"), {}).get("PTN", "0.00000000"),
        }
    return result


def _verify_signed_commit(
    network: Path, verifier: Path, height: int,
    *, tamper_app_hash: bool = False, proof_out: Path | None = None,
) -> dict:
    if height < 2:
        raise RuntimeError("commit verification requires at least height 2")
    store = MainnetChainStore(network / "node0" / "whalez-state")
    prior = store._load_block(height - 2)
    expected = _app_hash(
        height - 1, prior["block_hash"],
        prior["resulting_state_root"], prior["economic_state_root"],
    )
    if tamper_app_hash:
        expected = "00" * 32
    cmd = [
        str(verifier),
        "--rpc", "http://127.0.0.1:26657",
        "--genesis", str(network / "node0" / "config" / "genesis.json"),
        "--height", str(height),
        "--expected-apphash", expected,
    ]
    if proof_out is not None:
        cmd.extend(("--proof-out", str(proof_out)))
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=20,
    )
    if tamper_app_hash:
        return {"tampered_expected_hash_rejected": result.returncode != 0}
    if result.returncode != 0:
        raise RuntimeError(
            "independent signed commit proof failed: " + result.stderr[:350]
        )
    decoded = json.loads(result.stdout)
    if decoded.get("verified") is not True:
        raise RuntimeError("cryptographic proof did not verify")
    return decoded


def run(
    network: Path, comet: Path, bridge: Path, verifier: Path, out: Path
) -> dict:
    if os.getenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", "").lower() == "true":
        raise RuntimeError("production mainnet explicitly forbidden")
    if not network.is_dir() or not (network / "devnet_manifest.json").exists():
        raise ValueError("devnet must be provisioned before starting")
    manifest = json.loads((network / "devnet_manifest.json").read_text())
    if manifest["network_chain_id"] != NETWORK or manifest["nodes"] != 4:
        raise ValueError("unexpected validator topology")
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    src = Path(__file__).resolve().parents[3]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src) + os.pathsep + str(src / "apps")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["WHALEZCHAIN_MAINNET_EXECUTION_ENABLED"] = "false"
    children: list = []
    # AF_UNIX sockaddr paths are limited to ~108 bytes on Linux. The review
    # checkout is much longer; create a private short socket directory.
    socket_root = Path.home() / f".wcz-abci-{os.getpid()}"
    socket_root.mkdir(mode=0o700)
    report = {
        "network": NETWORK,
        "real_funds": False,
        "mainnet_activation": False,
        "source": "real CometBFT processes + WhalezChain state machine",
        "results": {},
    }
    try:
        for i in range(4):
            node = network / f"node{i}"
            socket_path = socket_root / f"n{i}.sock"
            if socket_path.exists():
                raise RuntimeError("existing backend socket; refusing unsafe reuse")
            _start([
                sys.executable, "-m",
                "whalezchain_orchestrator.mainnet.cometbft_abci_server",
                "--store", str(node / "whalez-state"),
                "--socket", str(socket_path),
                "--network-chain-id", NETWORK,
            ], env, out / f"python-node{i}.log", children)
        time.sleep(1)
        for i in range(4):
            _start([
                str(bridge), "--listen", f"tcp://127.0.0.1:{26658 + i * 10}",
                "--backend-socket", str(socket_root / f"n{i}.sock"),
            ], env, out / f"abci-node{i}.log", children)
        time.sleep(1)
        for i in range(4):
            node = network / f"node{i}"
            _start([
                str(comet), "--home", str(node), "--log_level", "error", "start",
            ], env, out / f"comet-node{i}.log", children)
        first = _await_height([0, 1, 2, 3], minimum=2, timeout=65)
        report["results"]["four_validators_produced_blocks"] = first

        # A real signed transaction is broadcast to CometBFT. No receipt is
        # accepted without independently replaying all four canonical stores.
        tx = signed_mainnet_transaction(
            tx_id="devnet-cometbft-transfer-20261123",
            sender_label="alice", recipient_label="bob",
            asset_symbol="PTN", amount="1.00000000", nonce=0,
            ordering_key="00000000000000000001",
        )
        raw = canonical_json(tx.signed_dict())
        broadcast = _rpc(26657, "broadcast_tx_sync?tx=0x" + raw.hex(), timeout=8)
        if int(broadcast["code"]) != 0:
            raise RuntimeError("real signed transaction rejected by CometBFT")
        starting_height = min(first.values())
        _await_height([0, 1, 2, 3], minimum=starting_height + 3, timeout=45)
        roots = _heads(network)
        report["results"]["committed_heads"] = roots
        if len({entry["state_root"] for entry in roots.values()}) != 1:
            raise RuntimeError("validator state-root divergence")
        common_whalez_height = min(entry["height"] for entry in roots.values())
        common_blocks = {
            MainnetChainStore(
                network / f"node{i}" / "whalez-state"
            )._load_block(common_whalez_height)["block_hash"]
            for i in range(4)
        }
        if len(common_blocks) != 1:
            raise RuntimeError("same-height block hash divergence")
        report["results"]["same_height_canonical_block_agreement"] = {
            "whalez_height": common_whalez_height,
            "block_hash": next(iter(common_blocks)),
        }
        if any(
            entry["alice_ptn"] != "9.00000000"
            or entry["bob_ptn"] != "1.00000000"
            for entry in roots.values()
        ):
            raise RuntimeError("signed transfer not recovered on all four validators")
        report["results"]["signed_transfer_replay"] = "PASS"

        # Query real CometBFT signed commits, not a fabricated Python Boolean.
        height = min(_height(i) for i in range(4)) - 1
        if height < 2:
            raise RuntimeError("insufficient signed commit history")
        commit = _rpc(26657, f"commit?height={height}")
        signatures = commit["signed_header"]["commit"]["signatures"]
        non_absent = sum(
            1 for signature in signatures
            if signature.get("block_id_flag") not in (1, "BLOCK_ID_FLAG_ABSENT")
        )
        report["results"]["comet_signed_commit"] = {
            "height": height,
            "signatures_reported": len(signatures),
            "non_absent": non_absent,
        }
        if non_absent < 3:
            raise RuntimeError("expected at least three validator commit signatures")
        proof_path = out / "signed-commit-evidence.json"
        report["results"]["independent_crypto_commit_proof"] = (
            _verify_signed_commit(
                network, verifier, height, proof_out=proof_path,
            )
        )
        if not proof_path.is_file():
            raise RuntimeError("no durable signed-header proof was exported")
        report["results"]["portable_signed_commit_proof"] = {
            "height": height,
            "signed_header_sha256": hashlib.sha256(
                proof_path.read_bytes()
            ).hexdigest(),
        }
        tampered = _verify_signed_commit(
            network, verifier, height, tamper_app_hash=True
        )
        if not tampered["tampered_expected_hash_rejected"]:
            raise RuntimeError("tampered application hash falsely verified")
        report["results"]["forged_app_hash_rejection"] = "PASS"

        # Stop a single consensus validator; the remaining 3/4 must continue
        # to commit. Application processes stay running, private only.
        victim = children[11][0]
        before_outage = min(_height(i) for i in (0, 1, 2))
        os.killpg(victim.pid, signal.SIGTERM)
        victim.wait(timeout=6)
        survivor_heights = _await_height(
            [0, 1, 2], minimum=before_outage + 2, timeout=45
        )
        report["results"]["three_of_four_outage_liveness"] = survivor_heights
        outage_proof_height = min(survivor_heights.values()) - 1
        report["results"]["three_of_four_signed_commit"] = (
            _verify_signed_commit(network, verifier, outage_proof_height)
        )

        # Recover the stopped validator from its own canonical state and
        # CometBFT persisted consensus data, never copying another node's DB.
        _start([
            str(comet), "--home", str(network / "node3"),
            "--log_level", "error", "start",
        ], env, out / "comet-node3-restarted.log", children)
        recovery_height = min(_height(i) for i in (0, 1, 2)) - 1
        _await_height([3], minimum=recovery_height, timeout=50)
        recovered = _heads(network)
        common_recovery_height = min(
            item["height"] for item in recovered.values()
        )
        recovery_hashes = {
            MainnetChainStore(
                network / f"node{i}" / "whalez-state"
            )._load_block(common_recovery_height)["block_hash"]
            for i in range(4)
        }
        if len(recovery_hashes) != 1:
            raise RuntimeError("recovered validator disagrees on common block")
        report["results"]["validator_restart_and_catchup"] = {
            "height": common_recovery_height,
            "common_block_hash": next(iter(recovery_hashes)),
        }

        # Quorum-loss negative control: when only 2 of 4 validators remain,
        # no new finalized block is possible. This is a real stop/start
        # experiment, not an artificial vote-count stub or network partition.
        for victim in (children[10][0], children[-1][0]):
            if victim.poll() is not None:
                raise RuntimeError("validator died before quorum-loss experiment")
            os.killpg(victim.pid, signal.SIGTERM)
            victim.wait(timeout=6)
        time.sleep(2.5)  # Allow any already-decided block to commit first.
        frozen = {i: _height(i) for i in (0, 1)}
        time.sleep(7)
        later = {i: _height(i) for i in (0, 1)}
        if later != frozen:
            raise RuntimeError(
                "consensus finalized without sufficient voting power"
            )
        report["results"]["two_of_four_quorum_loss_stalls_finality"] = {
            "before": frozen,
            "after": later,
            "verified": True,
        }

        # Restore the SAME validator data directories, not new identities.
        for index in (2, 3):
            _start([
                str(comet), "--home", str(network / f"node{index}"),
                "--log_level", "error", "start",
            ], env, out / f"comet-node{index}-quorum-restored.log", children)
        target = min(frozen.values()) + 2
        restored_heights = _await_height(
            [0, 1, 2, 3], minimum=target, timeout=55
        )
        common_restored_height = min(
            int(_heads(network)[index]["height"]) for index in range(4)
        )
        restored_blocks = {
            MainnetChainStore(
                network / f"node{i}" / "whalez-state"
            )._load_block(common_restored_height)["block_hash"]
            for i in range(4)
        }
        if len(restored_blocks) != 1:
            raise RuntimeError(
                "validator stores diverged after quorum restoration"
            )
        report["results"]["quorum_restoration_resumes_finality"] = {
            "heights": restored_heights,
            "common_whalez_height": common_restored_height,
            "common_block_hash": next(iter(restored_blocks)),
        }
        report["result"] = "PASS_INTERNAL_DEVNET"
        return report
    except BaseException as exc:
        report["result"] = "FAIL"
        report["failure_class"] = type(exc).__name__
        report["failure"] = str(exc)[:500]
        raise
    finally:
        _stop(children)
        for socket_file in socket_root.glob("n*.sock"):
            socket_file.unlink(missing_ok=True)
        socket_root.rmdir()
        (out / "e2e-receipt.json").write_text(
            json.dumps(report, sort_keys=True, indent=2) + "\n"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--network", required=True, type=Path)
    parser.add_argument("--comet", required=True, type=Path)
    parser.add_argument("--bridge", required=True, type=Path)
    parser.add_argument("--verifier", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run(args.network, args.comet, args.bridge, args.verifier, args.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
