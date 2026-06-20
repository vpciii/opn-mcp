"""get_updates_available reports pending updates from the package count.

Regression for the inverted-boolean bug: OPNsense's firmware status
returns status="ok" when there is *nothing* to update and other strings
(e.g. "update", "upgrade") when there are. The tool keyed
`updates_available` off `status == "ok"`, so a box with dozens of
pending packages reported `updates_available: False` — the same bug that
was already fixed in get_security_digest() but missed here.
"""

import asyncio

import httpx

import server


def _firmware_status(**overrides):
    """A /core/firmware/status payload with no pending work by default."""
    status = {
        "status": "ok",
        "status_msg": "There are no updates available on the selected mirror.",
        "product_version": "26.1.9",
        "last_check": "Sat Jun 20 09:00:04 EDT 2026",
        "upgrade_packages": [],
        "new_packages": [],
        "reinstall_packages": [],
        "remove_packages": [],
    }
    status.update(overrides)
    return status


def _serve(status):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/core/firmware/status":
            return httpx.Response(200, json=status)
        return httpx.Response(404, json={})

    return handler


async def test_pending_updates_are_reported_despite_non_ok_status(
    mock_opnsense, clean_env
):
    # Regression: 37 upgrades + 1 new, status="update" (not "ok").
    # The old `status == "ok"` check returned False here, masking updates.
    status = _firmware_status(
        status="update",
        status_msg="There are 38 updates available, ... This update requires a reboot.",
        upgrade_packages=[{"name": f"pkg{i}"} for i in range(37)],
        new_packages=[{"name": "py313-requests-unixsocket"}],
    )
    mock_opnsense(_serve(status))

    result = await server.get_updates_available()

    assert result.get("updates_available") is True, result
    assert result["package_counts"]["upgrade"] == 37
    assert result["package_counts"]["new"] == 1


async def test_no_updates_when_no_packages_pending(mock_opnsense, clean_env):
    # The clean case: status="ok" and empty package lists -> no updates.
    mock_opnsense(_serve(_firmware_status()))

    result = await server.get_updates_available()

    assert result.get("updates_available") is False, result
    assert result["package_counts"]["upgrade"] == 0
    assert result["package_counts"]["new"] == 0


def _recording_serve(status, calls):
    """Like _serve, but records (method, path) and answers the check POST.

    The async firmware-check trigger lives at /core/firmware/check; the
    cached status read lives at /core/firmware/status.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/api/core/firmware/check":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/api/core/firmware/status":
            return httpx.Response(200, json=status)
        return httpx.Response(404, json={})

    return handler


async def test_refresh_triggers_a_firmware_check_before_reading_status(
    mock_opnsense, clean_env, monkeypatch
):
    # refresh=True must POST /core/firmware/check to kick off a fresh check
    # before reading the cached status. Without it, the daily-summary task's
    # "refresh first" step is a silent no-op and update counts stay stale —
    # the failure PR #13 set out to fix. (Adversarial review of PR #13.)
    async def _instant(_seconds):  # skip the real 3s grace-period wait
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant)
    calls: list[tuple[str, str]] = []
    mock_opnsense(_recording_serve(_firmware_status(), calls))

    await server.get_updates_available(refresh=True)

    assert ("POST", "/api/core/firmware/check") in calls, calls


async def test_default_does_not_trigger_a_firmware_check(mock_opnsense, clean_env):
    # refresh defaults to False: read the cached status only, never POST a
    # check. The hourly security-check task depends on this (no mirror hit
    # per run — see its "deliberately NO refresh" step).
    calls: list[tuple[str, str]] = []
    mock_opnsense(_recording_serve(_firmware_status(), calls))

    await server.get_updates_available()

    assert ("POST", "/api/core/firmware/check") not in calls, calls
