"""Permissioned UNIX-socket wallet read adapter for internal WhalezChain devnets.

No TCP listener; socket owner-only (0600) in an owner-only directory.
Owner-signed account query required on every request; no private signing
material, wallet registration, transfers, payroll or minting on this surface.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import socketserver
import stat

from .chain_store import MainnetChainStore
from .private_wallet_read import (
    PrivateWalletReadError, TrustedFinalityCheckpoint, query_verified_wallet,
)


MAX_REQUEST_BYTES = 16384


class PrivateWalletHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        # Never log wallet identity or signatures on the private adapter.
        return

    def _reply(self, status: int, body: dict) -> None:
        payload = json.dumps(
            body, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        self._reply(405, {"ok": False, "error": "signed_post_only"})

    def do_POST(self) -> None:
        if self.path != "/v1/private/wallet/query":
            self._reply(404, {"ok": False, "error": "unknown_private_wallet_route"})
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise PrivateWalletReadError("invalid_wallet_query_request_size")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise PrivateWalletReadError("incomplete_wallet_query")
            def unique_keys(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise PrivateWalletReadError("duplicate_wallet_query_key")
                    result[key] = value
                return result
            request = json.loads(raw, object_pairs_hook=unique_keys)
            result = query_verified_wallet(
                self.server.store, request,
                trusted_finality=self.server.trusted_finality,
            )
        except (PrivateWalletReadError, ValueError, TypeError, KeyError):
            self._reply(403, {"ok": False, "error": "private_wallet_query_denied"})
        except Exception:
            self._reply(503, {"ok": False, "error": "canonical_wallet_unavailable"})
        else:
            self._reply(200, result)


class PrivateWalletUnixServer(socketserver.UnixStreamServer):
    allow_reuse_address = False

    def __init__(
        self, socket_path: str | Path, store: MainnetChainStore,
        trusted_finality: TrustedFinalityCheckpoint | None = None,
    ):
        self.store = store
        self.trusted_finality = trusted_finality
        path = Path(socket_path)
        parent = path.parent
        info = parent.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise PrivateWalletReadError("private_wallet_socket_parent_not_owner_only")
        if path.exists() or path.is_symlink():
            raise PrivateWalletReadError("private_wallet_socket_already_exists")
        os.umask(0o077)
        super().__init__(str(path), PrivateWalletHandler)
        os.chmod(path, 0o600)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--trusted-comet-genesis", type=Path)
    parser.add_argument("--signed-header-proof", type=Path)
    parser.add_argument("--verifier-binary", type=Path)
    parser.add_argument("--signed-header-height", type=int)
    args = parser.parse_args()
    finality_fields = (
        args.trusted_comet_genesis, args.signed_header_proof,
        args.verifier_binary, args.signed_header_height,
    )
    if any(item is not None for item in finality_fields):
        if any(item is None for item in finality_fields):
            raise PrivateWalletReadError("partial_finality_trust_context_disallowed")
        trusted_finality = TrustedFinalityCheckpoint(
            comet_genesis=args.trusted_comet_genesis,
            signed_header_proof=args.signed_header_proof,
            verifier_binary=args.verifier_binary,
            signed_header_height=args.signed_header_height,
        )
    else:
        trusted_finality = None
    store = MainnetChainStore(args.store)
    if store.load_genesis()["authority_config"].get("mode") != "test":
        raise PrivateWalletReadError("private_wallet_server_devnet_only")
    server = PrivateWalletUnixServer(args.socket, store, trusted_finality)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        args.socket.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
