"""Private, local-only UNIX-socket ABCI++ bridge for CometBFT.

No TCP listener, no public endpoints, no financial mainnet activation.
The consensus engine talks ABCI socket to the Go front end; this service
executes the existing WhalezChain Python application state machine.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import UnixStreamServer
from typing import Any

from .cometbft_state_machine import CometABCIError, WhalezCometApplication


MAX_BODY_BYTES = 2_000_000


class PrivateABCIHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        # Never log transaction contents or private runtime paths.
        return

    def _respond(self, code: int, result: dict[str, Any]) -> None:
        payload = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path != "/info":
            self._respond(404, {"error": "unknown endpoint"})
            return
        try:
            self._respond(200, self.server.app.info())
        except Exception as exc:
            self._respond(503, {"error": type(exc).__name__})

    def do_POST(self) -> None:
        try:
            size = int(self.headers.get("Content-Length", "-1"))
            if size < 0 or size > MAX_BODY_BYTES:
                raise CometABCIError("request body exceeds admission size limit")
            raw = self.rfile.read(size)
            request = json.loads(raw)
            if not isinstance(request, dict):
                raise CometABCIError("invalid RPC object")
            app = self.server.app
            path = self.path
            if path == "/init":
                result = app.init_chain(
                    request["chain_id"], request["app_genesis_hash"]
                )
            elif path == "/check":
                result = {"accepted": app.check_tx(_decode_b64(request["tx"]))}
            elif path == "/prepare":
                accepted = app.prepare_proposal(
                    _decode_txs(request["txs"]), int(request["max_bytes"])
                )
                result = {"txs": [_encode_b64(item) for item in accepted]}
            elif path == "/process":
                result = {
                    "accepted": app.process_proposal(_decode_txs(request["txs"]))
                }
            elif path == "/finalize":
                result = app.finalize_block(
                    height=int(request["height"]),
                    block_hash=request["block_hash"],
                    timestamp=request["timestamp"],
                    proposer_address=request["proposer_address"],
                    raws=_decode_txs(request["txs"]),
                )
            elif path == "/commit":
                if request:
                    raise CometABCIError("Commit accepts no caller parameters")
                result = app.commit()
            else:
                self._respond(404, {"error": "unknown endpoint"})
                return
            self._respond(200, result)
        except (CometABCIError, ValueError, TypeError, KeyError, binascii.Error):
            self._respond(422, {"error": "invalid_or_unauthorized_abci_request"})
        except Exception as exc:
            self._respond(503, {"error": type(exc).__name__})


def _encode_b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _decode_b64(encoded: str) -> bytes:
    if not isinstance(encoded, str):
        raise CometABCIError("base64 transaction must be a string")
    return base64.b64decode(encoded, validate=True)


def _decode_txs(encoded: list[str]) -> tuple[bytes, ...]:
    if not isinstance(encoded, list) or len(encoded) > 500:
        raise CometABCIError("invalid transaction collection")
    return tuple(_decode_b64(item) for item in encoded)


class PrivateABCIUnixServer(UnixStreamServer):
    allow_reuse_address = False

    def __init__(self, path: str, app: WhalezCometApplication):
        self.app = app
        socket_path = Path(path)
        if not socket_path.parent.is_dir():
            raise CometABCIError("UNIX socket parent directory is absent")
        if socket_path.exists() or socket_path.is_symlink():
            raise CometABCIError("UNIX socket path already exists")
        super().__init__(str(socket_path), PrivateABCIHandler)
        os.chmod(socket_path, 0o600)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--network-chain-id", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    app = WhalezCometApplication(args.store, args.network_chain_id)
    server = PrivateABCIUnixServer(args.socket, app)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        Path(args.socket).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
