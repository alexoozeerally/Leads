"""Localhost fixture site server for the offline end-to-end demo.

The environment's egress policy blocks crawling arbitrary public sites, so
``run-sample`` serves realistic fixture websites on localhost and crawls those.
This exercises the *real* crawler, a *real* headless browser, and *real*
screenshots — only the target sites are local fixtures.

To make the audit faithful, sites are served over **HTTPS** (a throwaway
self-signed cert) so the security check reflects the fixtures' intent, and any
path (e.g. ``/services``) returns the home page with 200 so navigation links
resolve instead of 404-ing. The crawler is configured to ignore the self-signed
cert (as it would when detecting SSL issues itself).
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import socket
import ssl
import subprocess
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

FIXTURE_SITES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "sites"

_cert_cache: tuple[str, str] | None = None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _self_signed_cert() -> tuple[str, str]:
    """Generate (once) a throwaway self-signed cert; return (cert_path, key_path)."""
    global _cert_cache
    if _cert_cache is not None:
        return _cert_cache
    tmp = Path(tempfile.mkdtemp(prefix="leadfinder-cert-"))
    cert, key = tmp / "cert.pem", tmp / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
        ],
        check=True,
        capture_output=True,
    )
    _cert_cache = (str(cert), str(key))
    return _cert_cache


class _FixtureHandler(http.server.SimpleHTTPRequestHandler):
    """Serves files; falls back to the per-server home page for unknown paths."""

    def __init__(self, *args, home_file: str = "index.html", **kwargs) -> None:
        # Must be set before super().__init__, which processes the request.
        self._home_file = home_file
        super().__init__(*args, **kwargs)

    def log_message(self, *args) -> None:  # silence per-request logging
        pass

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        path = self.translate_path(self.path)
        if not Path(path).is_file():
            # Unknown route (e.g. /services) -> serve the home page with 200.
            self.path = "/" + self._home_file
        return super().do_GET()


def _make_server(directory: Path, home_file: str, tls: bool) -> http.server.ThreadingHTTPServer:
    handler = functools.partial(_FixtureHandler, directory=str(directory), home_file=home_file)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", _free_port()), handler)
    if tls:
        cert, key = _self_signed_cert()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=cert, keyfile=key)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@contextlib.contextmanager
def serve_distinct_sites(
    home_files: list[str], directory: Path | None = None, tls: bool = True
) -> Iterator[list[str]]:
    """Serve ``directory`` on one HTTPS port per entry in ``home_files``.

    Each port is a distinct host, so demo businesses that share a fixture
    directory still get distinct websites (and distinct dedupe keys), mirroring
    how real businesses live on separate domains. Returns the base URLs.
    """
    directory = directory or FIXTURE_SITES_DIR
    scheme = "https" if tls else "http"
    servers: list[http.server.ThreadingHTTPServer] = []
    urls: list[str] = []
    try:
        for home in home_files:
            server = _make_server(directory, home, tls)
            servers.append(server)
            urls.append(f"{scheme}://127.0.0.1:{server.server_address[1]}")
        yield urls
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
