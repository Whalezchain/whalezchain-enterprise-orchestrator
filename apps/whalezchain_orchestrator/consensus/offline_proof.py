"""Verify exported signed-commit evidence without contacting a validator.

Independent pinned genesis and existing native canonical WhalezChain store
supply the trust anchors. This is devnet audit evidence, never a financial
execution approval or permission to enable production mainnet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from whalezchain_orchestrator.consensus.devnet_bootstrap import NETWORK
from whalezchain_orchestrator.mainnet.chain_store import MainnetChainStore
from whalezchain_orchestrator.mainnet.cometbft_state_machine import _app_hash


class OfflineProofError(ValueError):
    pass


def _run_verifier(
    verifier: Path, trusted_genesis: Path, height: int,
    expected_hash: str, proof: Path,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            str(verifier), "--proof-in", str(proof),
            "--genesis", str(trusted_genesis),
            "--height", str(height),
            "--expected-apphash", expected_hash,
        ],
        capture_output=True, text=True, timeout=20, check=False,
    )


def verify_and_receipt(
    network: Path, verifier: Path, height: int, proof: Path, output: Path,
) -> dict:
    if os.getenv("WHALEZCHAIN_MAINNET_EXECUTION_ENABLED", "").lower() == "true":
        raise OfflineProofError("production financial release is disabled")
    if height < 2:
        raise OfflineProofError("header cannot certify a pre-genesis WhalezChain block")
    manifest = json.loads((network / "devnet_manifest.json").read_text())
    if manifest.get("network_chain_id") != NETWORK or manifest.get("nodes") != 4:
        raise OfflineProofError("only the canonical isolated four-validator devnet is supported")
    if output.exists() or output.is_symlink():
        raise OfflineProofError("refusing to overwrite prior evidence")
    if not proof.is_file() or proof.is_symlink() or proof.stat().st_size > 1_000_000:
        raise OfflineProofError("untrusted proof file")
    root = network / "node0" / "whalez-state"
    store = MainnetChainStore(root)
    canonical_genesis = store.load_genesis()
    if canonical_genesis["authority_config"].get("mode") != "test":
        raise OfflineProofError("not a synthetic test genesis")
    store.verify_chain()
    certified_whalez_block = height - 2
    block = store._load_block(certified_whalez_block)
    expected_hash = _app_hash(
        height - 1, block["block_hash"],
        block["resulting_state_root"], block["economic_state_root"],
    )
    genesis_path = network / "node0" / "config" / "genesis.json"
    result = _run_verifier(verifier, genesis_path, height, expected_hash, proof)
    if result.returncode != 0:
        raise OfflineProofError("cryptographic proof verification rejected")
    try:
        report = json.loads(result.stdout)
    except ValueError as exc:
        raise OfflineProofError("verifier returned invalid JSON") from exc
    if not (
        report.get("verified") is True
        and report.get("verification_mode") == "offline_signature_cryptographic"
        and report.get("certified_whalez_block_height") == certified_whalez_block
        and report.get("network_chain_id") == NETWORK
        and report.get("signed_votes_for_block", 0) >= 3
        and report.get("signed_header_prior_app_hash") == expected_hash
    ):
        raise OfflineProofError("verified proof does not bind to the canonical state")

    # Three explicit fail-closed controls, using the same offline binary.
    false_hash = _run_verifier(
        verifier, genesis_path, height, "00" * 32, proof
    )
    if false_hash.returncode == 0:
        raise OfflineProofError("modified expected state falsely accepted")
    false_height = _run_verifier(
        verifier, genesis_path, height + 1, expected_hash, proof
    )
    if false_height.returncode == 0:
        raise OfflineProofError("replayed proof accepted for another height")

    document = json.loads(proof.read_text())
    if not isinstance(document.get("signed_header"), dict):
        raise OfflineProofError("invalid signed-header proof schema")
    document["signed_header"]["header"]["chain_id"] = "FORGED-NETWORK"
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(output.parent, 0o700)
    forged_path = output.parent / "forged-header-negative-control.json"
    if forged_path.exists() or forged_path.is_symlink():
        raise OfflineProofError("existing forged negative-control path")
    try:
        descriptor = os.open(
            forged_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(document, file, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        tampered = _run_verifier(
            verifier, genesis_path, height, expected_hash, forged_path
        )
        if tampered.returncode == 0:
            raise OfflineProofError("forged signed header falsely accepted")
    finally:
        forged_path.unlink(missing_ok=True)

    receipt = {
        "schema": "whalezchain.cometbft.offline-proof-audit.v1",
        "verdict": "VERIFIED_INTERNAL_DEVNET_ONLY",
        "verification_mode": "OFFLINE_NO_COMET_RPC",
        "network_chain_id": NETWORK,
        "signed_header_height": height,
        "certified_whalez_block_height": certified_whalez_block,
        "canonical_whalez_block_hash": block["block_hash"],
        "canonical_state_root": block["resulting_state_root"],
        "canonical_economic_root": block["economic_state_root"],
        "canonical_application_hash": expected_hash,
        "trusted_comet_genesis_sha256": hashlib.sha256(
            genesis_path.read_bytes()
        ).hexdigest(),
        "proof_sha256": hashlib.sha256(proof.read_bytes()).hexdigest(),
        "valid_validator_signatures": report["signed_votes_for_block"],
        "negative_controls": {
            "forged_header_rejected": True,
            "wrong_state_root_rejected": True,
            "wrong_header_height_rejected": True,
        },
        "real_financial_operations": False,
        "production_mainnet_certified": False,
    }
    payload = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    with tempfile.NamedTemporaryFile(
        dir=output.parent, prefix=".offline-proof-", delete=False
    ) as file:
        temporary = Path(file.name)
        os.chmod(temporary, 0o600)
        file.write(payload)
        file.flush()
        os.fsync(file.fileno())
    try:
        # Exclusive creation prevents overwriting another receipt, even when
        # its path is created after the initial check. Partial crash writes
        # remain invalid JSON and can never be accepted as valid evidence.
        descriptor = os.open(
            output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        try:
            with os.fdopen(descriptor, "wb") as destination:
                destination.write(payload)
                destination.flush()
                os.fsync(destination.fileno())
            directory_fd = os.open(
                output.parent, os.O_RDONLY | os.O_DIRECTORY
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except BaseException:
            output.unlink(missing_ok=True)
            raise
    finally:
        temporary.unlink(missing_ok=True)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--network", required=True, type=Path)
    parser.add_argument("--verifier", required=True, type=Path)
    parser.add_argument("--height", required=True, type=int)
    parser.add_argument("--proof", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = verify_and_receipt(
        args.network, args.verifier, args.height, args.proof, args.output
    )
    print(json.dumps({
        "verdict": result["verdict"],
        "certified_whalez_block_height":
            result["certified_whalez_block_height"],
        "negative_controls": result["negative_controls"],
        "production_mainnet_certified": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
