"""HTTP/2 transport regression (OPNsense 26.7 chunked-framing bug, ADR 0010).

OPNsense 26.7's web server emits malformed HTTP/1.1 chunked framing once
a response crosses a size threshold (observed live 2026-07-17:
`RemoteProtocolError: malformed chunk footer` with stray content bytes
where the CRLF terminator belongs, different bytes each run). The GUI
negotiates HTTP/2, whose length-prefixed DATA frames have no chunked
framing to corrupt — so the client must prefer h2.

The server here reproduces that failure mode at the protocol level: over
HTTP/1.1 it answers with a chunk that under-declares its size (content
bytes land where the footer belongs — the live 26.7 signature); over h2
it answers correctly. A client that does not negotiate h2 cannot read it.
"""

import asyncio
import ssl

import h2.config
import h2.connection
import h2.events
import pytest
import trustme

import server

BODY = b'{"ok": true}'


@pytest.fixture
def ca():
    return trustme.CA()


@pytest.fixture
async def chunk_mangling_api_server(ca):
    """HTTPS server with 26.7's failure mode: broken http/1.1, good h2.

    Yields "127.0.0.1:<port>" for use as OPNSENSE_HOST.
    """
    cert = ca.issue_cert("127.0.0.1")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    cert.configure_cert(ctx)
    ctx.set_alpn_protocols(["h2", "http/1.1"])

    async def serve_h1_malformed(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        # The chunk header declares 4 bytes but 12 follow, so content
        # bytes sit where the b"\r\n" footer belongs.
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n"
            b"4\r\n" + BODY + b"\r\n0\r\n\r\n"
        )
        await writer.drain()

    async def serve_h2(reader, writer):
        conn = h2.connection.H2Connection(
            config=h2.config.H2Configuration(client_side=False)
        )
        conn.initiate_connection()
        writer.write(conn.data_to_send())
        await writer.drain()
        while True:
            data = await reader.read(65536)
            if not data:
                return
            for event in conn.receive_data(data):
                if isinstance(event, h2.events.RequestReceived):
                    conn.send_headers(
                        event.stream_id,
                        [
                            (":status", "200"),
                            ("content-type", "application/json"),
                            ("content-length", str(len(BODY))),
                        ],
                    )
                    conn.send_data(event.stream_id, BODY, end_stream=True)
            out = conn.data_to_send()
            if out:
                writer.write(out)
                await writer.drain()

    async def handle(reader, writer):
        try:
            ssl_obj = writer.get_extra_info("ssl_object")
            if ssl_obj.selected_alpn_protocol() == "h2":
                await serve_h2(reader, writer)
            else:
                await serve_h1_malformed(reader, writer)
        except Exception:
            pass
        finally:
            writer.close()

    srv = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=ctx)
    port = srv.sockets[0].getsockname()[1]
    yield f"127.0.0.1:{port}"
    srv.close()
    await srv.wait_closed()


async def test_get_survives_chunk_mangled_http1_by_negotiating_h2(
    chunk_mangling_api_server, ca, tmp_path, clean_env
):
    # Red before ADR 0010 (client speaks only http/1.1 and trips on the
    # malformed footer); green once the client negotiates h2.
    bundle = tmp_path / "ca.pem"
    ca.cert_pem.write_to_path(bundle)
    clean_env.setenv("OPNSENSE_HOST", chunk_mangling_api_server)
    clean_env.setenv("OPNSENSE_CA_BUNDLE", str(bundle))

    assert await server._get("/core/system/status") == {"ok": True}
