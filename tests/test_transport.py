"""Transport posture (spec SC-1): stdio only, no network listener.

The SSE transport was retired by ADR 0007; the flag must fail loudly
with a pointer to the alternative, and no code path may start anything
but stdio.
"""

import pytest

import server


def test_sse_flag_exits_with_error():
    # SC-1
    with pytest.raises(SystemExit) as excinfo:
        server.main(["--sse"])
    msg = str(excinfo.value)
    assert "retired" in msg.lower()
    assert "stdio" in msg.lower()


def test_main_only_ever_runs_stdio(monkeypatch):
    # SC-1 — the only transport main() can start is stdio
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda transport: calls.append(transport))
    server.main([])
    assert calls == ["stdio"]
