"""A tiny localhost static server for the offline end-to-end demo.

The environment's egress policy blocks crawling arbitrary public sites, so
``run-sample`` serves realistic fixture websites on 127.0.0.1 (which bypasses the
proxy) and crawls those. This exercises the *real* crawler, a *real* headless
browser, and *real* screenshots — nothing about the pipeline is faked; only the
target sites are local fixtures.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import socket
import threading
from collections.abc import Iterator
from pathlib import Path

FIXTURE_SITES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "sites"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # silence per-request logging
        pass


@contextlib.contextmanager
def serve_fixture_sites(directory: Path | None = None) -> Iterator[str]:
    """Serve ``directory`` on a free localhost port; yield the base URL."""
    directory = directory or FIXTURE_SITES_DIR
    port = _free_port()
    handler = functools.partial(_QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


@contextlib.contextmanager
def serve_distinct_sites(count: int, directory: Path | None = None) -> Iterator[list[str]]:
    """Serve ``directory`` on ``count`` distinct localhost ports.

    Each port gives a distinct host, so demo businesses that reference the same
    fixture directory still get distinct websites (and thus distinct dedupe keys),
    mirroring how real businesses live on separate domains.
    """
    directory = directory or FIXTURE_SITES_DIR
    servers: list[http.server.ThreadingHTTPServer] = []
    urls: list[str] = []
    try:
        for _ in range(count):
            port = _free_port()
            handler = functools.partial(_QuietHandler, directory=str(directory))
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            servers.append(server)
            urls.append(f"http://127.0.0.1:{port}")
        yield urls
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
