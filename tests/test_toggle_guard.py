"""toggle_dnat_rule guard behavior (spec SC-5, SC-6, SC-7).

SC-5: synthetic anti-lockout rows are refused structurally.
SC-6: rules covering the firewall's own management path are refused.
SC-7: a server-side toggle failure is an error and apply is not called.

The FakeOpnsense handler stands in for the box and records every
request, so the tests can assert not just on the result but on which
API calls were (not) made.
"""

import httpx

import server


class FakeOpnsense:
    """Minimal d_nat API: getRule / toggleRule / apply / interface stats."""

    def __init__(self, rule=None, toggle_result=None, own_ip="203.0.113.7"):
        self.rule = rule if rule is not None else {}
        self.toggle_result = (
            toggle_result if toggle_result is not None else {"result": "Disabled"}
        )
        self.own_ip = own_ip
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append((request.method, path))
        if path.startswith("/api/firewall/d_nat/getRule/"):
            return httpx.Response(200, json={"rule": self.rule})
        if path.startswith("/api/firewall/d_nat/toggleRule/"):
            return httpx.Response(200, json=self.toggle_result)
        if path == "/api/firewall/d_nat/apply":
            return httpx.Response(200, json={"status": "ok"})
        if path == "/api/diagnostics/interface/getInterfaceStatistics":
            return httpx.Response(
                200, json={"statistics": {"wan": {"address": self.own_ip}}}
            )
        return httpx.Response(404, json={})

    def called(self, fragment: str) -> bool:
        return any(fragment in path for _, path in self.requests)


def ordinary_rule(**overrides):
    """A harmless port-forward: WAN:8443 → internal host."""
    rule = {
        "descr": "forward to media server",
        "nordr": "0",
        "destination": {"network": "203.0.113.7", "port": "8443"},
        "target": "10.0.0.50",
        "local-port": "8443",
    }
    rule.update(overrides)
    return rule


# --- SC-5: synthetic anti-lockout rows refused structurally ---


async def test_synthetic_lockout_uuid_is_refused(mock_opnsense, clean_env):
    # SC-5 — OPNsense's own anti-lockout rows have lockout_<n> pseudo-uuids
    fake = FakeOpnsense()
    mock_opnsense(fake)

    result = await server.toggle_dnat_rule("lockout_0", enabled=False)

    assert "error" in result, result
    assert "anti-lockout" in result["error"].lower()
    assert not fake.called("toggleRule"), "must refuse before any toggle attempt"
    assert not fake.called("apply")


async def test_dead_descr_guard_regression(mock_opnsense, clean_env):
    # SC-5 / SC-6 regression — the old guard read rule["description"], but
    # the API field is "descr": a rule literally described as the
    # anti-lockout rule, capturing the management path, sailed through.
    fake = FakeOpnsense(
        rule=ordinary_rule(
            descr="Anti-Lockout Rule",
            destination={"network": "203.0.113.7", "port": "443"},
        )
    )
    mock_opnsense(fake)

    result = await server.toggle_dnat_rule("0c5e9f86-aaaa-bbbb-cccc-000000000001", enabled=True)

    assert "error" in result, result
    assert not fake.called("toggleRule")


# --- SC-6: management-path rules refused ---


async def test_rule_covering_own_ip_and_api_port_is_refused(mock_opnsense, clean_env):
    # SC-6 — destination = firewall's own IPv4 + the API port this
    # server itself uses (default host has no port → 443)
    fake = FakeOpnsense(
        rule=ordinary_rule(destination={"network": "203.0.113.7", "port": "443"})
    )
    mock_opnsense(fake)

    result = await server.toggle_dnat_rule("0c5e9f86-aaaa-bbbb-cccc-000000000002", enabled=True)

    assert "error" in result, result
    assert "management" in result["error"].lower()
    assert not fake.called("toggleRule")
    assert not fake.called("apply")


async def test_rule_with_interface_ip_token_is_refused(mock_opnsense, clean_env):
    # SC-6 — "wanip"-style tokens are the firewall's own address
    fake = FakeOpnsense(
        rule=ordinary_rule(destination={"network": "wanip", "port": "443"})
    )
    mock_opnsense(fake)

    result = await server.toggle_dnat_rule("0c5e9f86-aaaa-bbbb-cccc-000000000003", enabled=True)

    assert "error" in result, result
    assert not fake.called("toggleRule")


async def test_ordinary_rule_still_toggles(mock_opnsense, clean_env):
    # pass-through — the guard must not block normal operation
    fake = FakeOpnsense(rule=ordinary_rule(), toggle_result={"result": "Enabled"})
    mock_opnsense(fake)

    result = await server.toggle_dnat_rule("0c5e9f86-aaaa-bbbb-cccc-000000000004", enabled=True)

    assert "error" not in result, result
    assert result["status"] == "enabled"
    assert fake.called("toggleRule")
    assert fake.called("apply")


# --- SC-7: server-side failure is an error; apply is not reached ---


async def test_failed_toggle_is_an_error_and_apply_is_skipped(
    mock_opnsense, clean_env
):
    # SC-7 — regression for the success-masking bug: OPNsense's
    # {"result": "failed"} was wrapped in a success-shaped response and
    # apply was still called
    fake = FakeOpnsense(rule=ordinary_rule(), toggle_result={"result": "failed"})
    mock_opnsense(fake)

    result = await server.toggle_dnat_rule("0c5e9f86-aaaa-bbbb-cccc-000000000005", enabled=False)

    assert "error" in result, result
    assert not fake.called("apply"), "apply must not run after a failed toggle"


async def test_missing_rule_is_an_error(mock_opnsense, clean_env):
    # SC-7 adjacent — getRule returning an empty rule (e.g. a uuid that
    # doesn't exist in the model) must not proceed to toggle
    fake = FakeOpnsense(rule={})
    mock_opnsense(fake)

    result = await server.toggle_dnat_rule("0c5e9f86-aaaa-bbbb-cccc-000000000006", enabled=True)

    assert "error" in result, result
    assert not fake.called("toggleRule")
