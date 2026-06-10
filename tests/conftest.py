"""Shared fixtures for the opn-mcp test suite.

No test in this suite talks to a real OPNsense box: API traffic is
routed through httpx.MockTransport by patching server._client.
"""

import httpx
import pytest

import server


@pytest.fixture
def mock_opnsense(monkeypatch):
    """Route the server's API calls through an httpx.MockTransport.

    Usage:
        def handler(request: httpx.Request) -> httpx.Response: ...
        mock_opnsense(handler)

    Returns the installed transport. Calls made via server._get /
    server._post (and any tool built on them) hit the handler instead
    of the network.
    """

    def install(handler):
        transport = httpx.MockTransport(handler)

        def patched_client() -> httpx.AsyncClient:
            return httpx.AsyncClient(
                base_url="https://opnsense.test/api",
                transport=transport,
            )

        monkeypatch.setattr(server, "_client", patched_client)
        return transport

    return install


@pytest.fixture
def clean_env(monkeypatch):
    """Remove all OPNSENSE_* variables so tests see bare defaults."""
    for var in (
        "OPNSENSE_HOST",
        "OPNSENSE_API_KEY",
        "OPNSENSE_API_SECRET",
        "OPNSENSE_VERIFY_SSL",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch
