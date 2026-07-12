"""Characterization tests for get_security_digest (spec: digest-coverage, SC-1).

get_security_digest sweeps several endpoints (audit log, firewall log,
services, firmware status, certs, pf state table) and emits a flat
`warnings` list that both scheduled monitors (docs/MONITORING.md)
fast-path on. These tests pin down which scenarios do and do not
produce a warning, against the mock transport only — no live firewall,
no changes to server.py.
"""

import json
import time

import httpx

import server

# --- Baseline fixtures: a clean system, no warnings anywhere ---

CLEAN_INTERFACES = {"statistics": {}}
CLEAN_SERVICES = {
    "rows": [{"name": "unbound", "description": "DNS resolver", "running": True, "id": "1"}]
}
CLEAN_FIRMWARE = {
    "status": "ok",
    "status_msg": "There are no updates available on the selected mirror.",
    "product_version": "24.1.9",
    "last_check": "Sun Jul 12 09:00:00 EDT 2026",
    "upgrade_packages": [],
    "new_packages": [],
    "reinstall_packages": [],
    "remove_packages": [],
}
CLEAN_CERTS = {"rows": []}
CLEAN_PF_STATES = {"current": 100, "limit": 200000}


def _filter_log_row(
    src_ip: str,
    dst_ip: str = "192.168.1.1",
    proto: str = "tcp",
    dst_port: str = "22",
    action: str = "block",
) -> dict:
    """A synthetic OPNsense filterlog CSV row (IPv4), matching the layout
    `_parse_filter_log` expects (see server.py's field-index docstring)."""
    parts = [
        "1", "0", "", "1234567890", "wan", "match", action, "in", "4",
        "0x0", "", "64", "12345", "0", "", "6", proto, "60",
        src_ip, dst_ip, "12345", dst_port,
    ]
    return {"timestamp": "2026-07-12T00:00:00", "line": ",".join(parts)}


def make_handler(
    *,
    login_rows=None,
    denied_rows=None,
    firewall_rows=None,
    services=None,
    firmware=None,
    certs=None,
    pf_states=None,
    config_rows=None,
):
    """Build a mock_opnsense handler routing on request.url.path (and, for
    the shared audit-log endpoint, the POST body's searchPhrase). Every
    argument defaults to a "clean" value so a single override produces
    exactly one scenario."""
    login_rows = login_rows if login_rows is not None else []
    denied_rows = denied_rows if denied_rows is not None else []
    firewall_rows = firewall_rows if firewall_rows is not None else []
    services = services if services is not None else CLEAN_SERVICES
    firmware = firmware if firmware is not None else CLEAN_FIRMWARE
    certs = certs if certs is not None else CLEAN_CERTS
    pf_states = pf_states if pf_states is not None else CLEAN_PF_STATES
    config_rows = config_rows if config_rows is not None else []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/diagnostics/interface/getInterfaceStatistics":
            return httpx.Response(200, json=CLEAN_INTERFACES)
        if path == "/api/core/service/search":
            return httpx.Response(200, json=services)
        if path == "/api/core/firmware/status":
            return httpx.Response(200, json=firmware)
        if path == "/api/trust/cert/search":
            return httpx.Response(200, json=certs)
        if path == "/api/diagnostics/firewall/pf_states":
            return httpx.Response(200, json=pf_states)
        if path == "/api/diagnostics/log/filter/latest":
            return httpx.Response(200, json={"rows": firewall_rows})
        if path == "/api/diagnostics/log/core/audit":
            body = json.loads(request.content or b"{}")
            phrase = body.get("searchPhrase", "")
            if phrase == "login":
                return httpx.Response(200, json={"rows": login_rows})
            if phrase == "denied":
                return httpx.Response(200, json={"rows": denied_rows})
            return httpx.Response(200, json={"rows": []})
        if path == "/api/diagnostics/log/core/system":
            return httpx.Response(200, json={"rows": config_rows})
        raise AssertionError(f"unexpected request: {request.method} {path}")

    return handler


async def test_clean_system_emits_no_warnings(mock_opnsense, clean_env):
    # SC-1 — clean case: absence of warnings, not just presence elsewhere.
    mock_opnsense(make_handler())

    digest = await server.get_security_digest()

    assert digest["warnings"] == [], digest["warnings"]
    assert digest["status"] == "ok"


async def test_failed_ui_logins_emit_warning(mock_opnsense, clean_env):
    # SC-1
    failed_rows = [
        {
            "timestamp": "2026-07-12T01:00:00",
            "line": "/index.php: Failed login for user 'admin' from: 198.51.100.5",
        },
        {
            "timestamp": "2026-07-12T01:00:05",
            "line": "/index.php: Failed login for user 'admin' from: 198.51.100.5",
        },
    ]
    mock_opnsense(make_handler(login_rows=failed_rows))

    digest = await server.get_security_digest()

    assert digest["info"]["auth"]["failed_count"] == 2
    assert any("failed UI login attempt" in w for w in digest["warnings"]), digest["warnings"]


async def test_denied_admin_actions_emit_warning(mock_opnsense, clean_env):
    # SC-1
    denied_rows = [
        {
            "timestamp": "2026-07-12T01:05:00",
            "line": "action denied configd.actions.firmware.upgrade for user 'attacker'",
        }
    ]
    mock_opnsense(make_handler(denied_rows=denied_rows))

    digest = await server.get_security_digest()

    assert digest["info"]["auth"]["denied_admin_actions"] == 1
    assert any("denied admin action" in w for w in digest["warnings"]), digest["warnings"]


async def test_stopped_service_emits_warning(mock_opnsense, clean_env):
    # SC-1
    services = {
        "rows": [
            {"name": "unbound", "description": "DNS resolver", "running": True, "id": "1"},
            {"name": "dhcpd", "description": "DHCP server", "running": False, "id": "2"},
        ]
    }
    mock_opnsense(make_handler(services=services))

    digest = await server.get_security_digest()

    assert digest["info"]["services"]["stopped_count"] == 1
    assert any("service(s) not running" in w for w in digest["warnings"]), digest["warnings"]


async def test_expiring_certificate_emits_warning(mock_opnsense, clean_env):
    # SC-1
    near_future = int(time.time()) + 10 * 86400  # 10 days out, < default 30d threshold
    certs = {
        "rows": [
            {
                "uuid": "abc-123",
                "descr": "wan-gui-cert",
                "commonname": "opnsense.example.com",
                "in_use": "1",
                "valid_from": str(int(time.time()) - 86400),
                "valid_to": str(near_future),
            }
        ]
    }
    mock_opnsense(make_handler(certs=certs))

    digest = await server.get_security_digest()

    assert len(digest["info"]["certificates"]["expiring_soon"]) == 1
    assert any("expires in" in w for w in digest["warnings"]), digest["warnings"]


async def test_pending_updates_emit_warning(mock_opnsense, clean_env):
    # SC-1
    firmware = dict(
        CLEAN_FIRMWARE,
        status="upgrade",
        status_msg="There is a total of 1 package updated.",
        upgrade_packages=[{"name": "opnsense"}],
    )
    mock_opnsense(make_handler(firmware=firmware))

    digest = await server.get_security_digest()

    assert digest["info"]["updates"]["available"] is True
    assert any("Pending OPNsense" in w for w in digest["warnings"]), digest["warnings"]


async def test_wan_blocks_below_threshold_emit_no_warning(mock_opnsense, clean_env):
    # SC-1 — suppressed-noise regime: < 200 WAN-origin blocks, no single
    # source concentrated enough to look like a scan. Deliberate noise
    # suppression per docs/MONITORING.md; absence of warnings asserted.
    rows = []
    for i in range(5):
        src = f"1.2.3.{10 + i}"
        rows.extend(_filter_log_row(src) for _ in range(20))  # 5 * 20 = 100 total
    mock_opnsense(make_handler(firewall_rows=rows))

    digest = await server.get_security_digest()

    assert digest["info"]["firewall"]["wan_origin_count"] == 100
    assert digest["warnings"] == [], digest["warnings"]


async def test_wan_blocks_at_threshold_emit_warning(mock_opnsense, clean_env):
    # SC-1 — warning regime: single WAN source at the 200-block gate. The
    # assertion pins WHICH gate fired ("active scan/brute" — the >= 200
    # single-source gate), not just that some WAN warning appeared: the
    # >= 50 "focused scan" message shares the same prefix (review finding
    # on this PR).
    rows = [_filter_log_row("5.6.7.8") for _ in range(200)]
    mock_opnsense(make_handler(firewall_rows=rows))

    digest = await server.get_security_digest()

    assert digest["info"]["firewall"]["wan_origin_count"] == 200
    assert any("active scan/brute" in w for w in digest["warnings"]), digest["warnings"]


async def test_wan_focused_scan_regime_emits_medium_gate_warning(
    mock_opnsense, clean_env
):
    # SC-1 — the middle gate: a single source in the 50-199 regime fires
    # "focused scan", and provably NOT the >= 200 gate.
    rows = [_filter_log_row("5.6.7.8") for _ in range(60)]
    mock_opnsense(make_handler(firewall_rows=rows))

    digest = await server.get_security_digest()

    assert any("focused scan" in w for w in digest["warnings"]), digest["warnings"]
    assert not any("active scan/brute" in w for w in digest["warnings"])


async def test_wan_distributed_flood_regime_emits_flood_warning(
    mock_opnsense, clean_env
):
    # SC-1 — the distributed gate: >= 1000 total WAN blocks with every
    # source below the 50-hit focused threshold fires "distributed flood"
    # (and neither single-source gate).
    rows = []
    for i in range(25):
        src = f"9.9.{i}.1"
        rows.extend(_filter_log_row(src) for _ in range(40))  # 25 * 40 = 1000
    mock_opnsense(make_handler(firewall_rows=rows))

    digest = await server.get_security_digest()

    assert any("distributed flood" in w for w in digest["warnings"]), digest["warnings"]
    assert not any("single source" in w for w in digest["warnings"])
