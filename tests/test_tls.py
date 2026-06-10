"""TLS verification behavior (spec SC-2, SC-3, SC-4).

Handshake-level tests run a real TLS server on 127.0.0.1 with certs
minted by trustme — no external network. The server speaks just enough
HTTP/1.1 for httpx to complete one GET.
"""

import asyncio
import ssl

import pytest
import trustme

import server


@pytest.fixture
def ca():
    return trustme.CA()


@pytest.fixture
async def tls_api_server(ca):
    """HTTPS server answering any request with 200 {"ok": true}.

    Yields "127.0.0.1:<port>" for use as OPNSENSE_HOST.
    """
    cert = ca.issue_cert("127.0.0.1")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    cert.configure_cert(ctx)

    async def handle(reader, writer):
        try:
            await reader.readuntil(b"\r\n\r\n")
            body = b'{"ok": true}'
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: %d\r\n"
                b"Connection: close\r\n\r\n%s" % (len(body), body)
            )
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    srv = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=ctx)
    port = srv.sockets[0].getsockname()[1]
    yield f"127.0.0.1:{port}"
    srv.close()
    await srv.wait_closed()


# --- SC-2: verification is the default; explicit false still opts out ---


def test_default_settings_verify_tls(clean_env):
    # SC-2
    s = server._settings()
    assert s.verify_ssl is True
    assert server._tls_verify(s) is True  # stock httpx verification, no custom context


def test_explicit_false_still_opts_out(clean_env):
    # SC-2 (the documented escape hatch)
    clean_env.setenv("OPNSENSE_VERIFY_SSL", "false")
    v = server._tls_verify(server._settings())
    assert isinstance(v, ssl.SSLContext)
    assert v.verify_mode == ssl.CERT_NONE
    assert v.check_hostname is False


# --- SC-3: OPNSENSE_CA_BUNDLE pins a private CA ---


async def test_ca_bundle_connects_to_private_ca_server(
    tls_api_server, ca, tmp_path, clean_env
):
    # SC-3 — a real handshake against a cert signed by the pinned CA
    bundle = tmp_path / "ca.pem"
    ca.cert_pem.write_to_path(bundle)
    clean_env.setenv("OPNSENSE_HOST", tls_api_server)
    clean_env.setenv("OPNSENSE_CA_BUNDLE", str(bundle))

    # the bundle must produce a *verifying* context (not an opt-out)
    v = server._tls_verify(server._settings())
    assert isinstance(v, ssl.SSLContext)
    assert v.verify_mode == ssl.CERT_REQUIRED

    assert await server._get("/core/system/status") == {"ok": True}


# --- SC-4: verification failure names both remedies ---


async def test_verification_failure_message_names_remedies(
    tls_api_server, clean_env
):
    # SC-4 — same server, CA not pinned: must fail (proving SC-2's
    # default does verify) with a message naming both remedies
    clean_env.setenv("OPNSENSE_HOST", tls_api_server)

    with pytest.raises(Exception) as excinfo:
        await server._get("/core/system/status")
    msg = str(excinfo.value)
    assert "OPNSENSE_CA_BUNDLE" in msg
    assert "OPNSENSE_VERIFY_SSL=false" in msg
