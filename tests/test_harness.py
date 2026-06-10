"""Harness smoke tests.

test_suite_runs_async_against_mock_transport verifies SC-9's substance
on the test side: the suite exists, the async runner works, and API
traffic is mockable without a real firewall. CI enforcement (runs on
every PR, fails on failure) lives in .github/workflows/ci.yml.
"""

import httpx

import server


async def test_suite_runs_async_against_mock_transport(mock_opnsense):
    # SC-9
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/core/system/status"
        return httpx.Response(200, json={"ok": True})

    mock_opnsense(handler)
    assert await server._get("/core/system/status") == {"ok": True}


async def test_post_helper_uses_mock_transport(mock_opnsense):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"echo": request.url.path})

    mock_opnsense(handler)
    result = await server._post("/diagnostics/x/y", json={"a": 1})
    assert result == {"echo": "/api/diagnostics/x/y"}
