# ADR 0010: HTTP/2 for the OPNsense API client

- **Status:** Accepted
- **Date:** 2026-07-17
- **Deciders:** Vince Ciganik

## Context

The firewall's upgrade to OPNsense 26.7 broke every large API response:
past roughly 100 KB (log fetches beyond ~250 rows), the web server emits
malformed HTTP/1.1 chunked framing — content bytes appear where a
chunk's CRLF footer belongs, with different stray bytes each run — and
httpx fails with `RemoteProtocolError: malformed chunk footer`. Measured
live on 2026-07-17: firewall log at 250 rows OK / 350 fails; audit log
at 500 rows OK / 2000 fails. This blinded the security digest's
firewall-blocks section (`window_lines=500`) and would degrade the daily
summary's audit sweep (`window_lines=2000`) too. The bug is server-side:
it appeared at the moment of the upgrade, with no client change, and no
proxy in the path (`trust_env=False`, LAN-direct).

No upstream OPNsense report existed as of 2026-07-17. We need the
monitoring signal back now, without waiting on an upstream fix.

## Decision

The API client negotiates **HTTP/2**: `httpx.AsyncClient(http2=True)`
plus the **`httpx[http2]` extra** (pulls `h2`, `hpack`, `hyperframe` —
the python-hyper stack). HTTP/2 carries bodies in length-prefixed DATA
frames; there is no chunked transfer encoding to mis-frame, so the
broken code path in 26.7 is bypassed entirely.

The flag alone turned out not to engage: httpcore hardcodes the ALPN
offer as `["http/1.1", "h2"]`, and lighttpd (OPNsense's GUI server)
selects the *client's* first preference — verified live with `openssl
s_client` in both orders. So `_tls_verify` now always returns our own
`ssl.SSLContext` (stock-verifying by default, unchanged CA-pinning and
opt-out modes) whose `set_alpn_protocols` re-orders any offer h2-first
(`_prefer_h2`). If a future OPNsense drops h2 support, ALPN falls back
to http/1.1 — behavior then reverts to whatever the server's HTTP/1.1
framing does, no client change needed.

## Alternatives considered

- **Page log fetches (`rowCount`/`current`) under the size threshold** —
  no new dependency, but the `latest` log origin's pagination semantics
  are unverified (its `total` tracks the requested window, suggesting it
  may not page like a normal bootgrid), pages of a hot filterlog shift
  between requests (duplicate/missed rows), and every other large
  endpoint would stay broken. Rejected as riskier and narrower.
- **Wait for an upstream OPNsense fix** — right call eventually (we
  should file the bug), but the WAN scan/brute-force signal is blind
  today and release cadence is months.
- **Tolerant re-parsing of the broken framing** — httpx/h11 offer no
  hook for it; hand-rolling HTTP parsing to accept corrupt framing is
  exactly the wrong kind of cleverness for a security monitoring tool.

## Consequences

- Easier: all window sizes work again, including the daily summary's
  `window_lines=2000`; the whole API surface (not just logs) is immune
  to the 26.7 chunked-framing bug; connection reuse gets cheaper if we
  ever batch calls (h2 multiplexing).
- Harder: three new (small, pure-Python, actively maintained,
  MIT-licensed) transitive dependencies from the python-hyper stack;
  ADR 0004's "exactly two runtime packages" is amended by this ADR —
  direct dependencies stay at two (`mcp[cli]`, `httpx[http2]`).
- The h2-first ALPN re-ordering shims a context method behind
  httpcore's back; if httpcore ever exposes ALPN order (or stops
  setting it on user contexts), `_prefer_h2` should be revisited. The
  default-verify mode now returns our own context instead of httpx's
  `verify=True`, with the same verifying posture (asserted by SC-2's
  test).
- The Docker image must be rebuilt for the fix to reach running
  deployments (README troubleshooting covers this).

## References

- `server.py` `_client()`; regression test `tests/test_http2.py`
  (local server reproducing the 26.7 framing bug over http/1.1,
  correct over h2)
- ADR 0004 (dependency posture — amended, not superseded)
- Live diagnosis 2026-07-17: `get_firewall_blocks` /
  `diagnostics/log` bisect; ALPN check against the GUI
