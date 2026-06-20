"""get_updates_available reports pending updates from the package count.

Regression for the inverted-boolean bug: OPNsense's firmware status
returns status="ok" when there is *nothing* to update and other strings
(e.g. "update", "upgrade") when there are. The tool keyed
`updates_available` off `status == "ok"`, so a box with dozens of
pending packages reported `updates_available: False` — the same bug that
was already fixed in get_security_digest() but missed here.
"""

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
