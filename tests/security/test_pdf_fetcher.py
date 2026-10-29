"""PDF rendering never fetches anything: no file://, no network, only embedded data: URIs."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from escalate.export.pdf import fetch_allowed, html_to_pdf, pdf_available

needs_pdf = pytest.mark.skipif(not pdf_available(), reason="WeasyPrint system libraries missing")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "FILE:///etc/passwd",
        "http://169.254.169.254/latest/meta-data/",
        "https://evil.example/pixel.png",
        "ftp://evil.example/x",
        "//evil.example/x.css",
        "/etc/passwd",
        "javascript:alert(1)",
        " file:///etc/passwd",
    ],
)
def test_only_data_uris_are_allowed(url: str) -> None:
    assert not fetch_allowed(url)


def test_data_uris_are_allowed() -> None:
    assert fetch_allowed("data:image/png;base64,iVBORw0KGgo=")
    assert fetch_allowed("DATA:image/png;base64,iVBORw0KGgo=")


@needs_pdf
def test_rendering_does_not_fetch_files_or_network(tmp_path: object) -> None:
    hits: list[str] = []

    class Spy(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Spy)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        doc = (
            f'<link rel="stylesheet" href="http://127.0.0.1:{port}/a.css">'
            f'<style>@import url("http://127.0.0.1:{port}/b.css");'
            f'body{{background:url("http://127.0.0.1:{port}/c.png")}}</style>'
            f'<img src="http://127.0.0.1:{port}/d.png"><img src="file:///etc/passwd">'
            '<iframe src="file:///etc/hosts"></iframe><p>letter</p>'
        )
        pdf = html_to_pdf(doc)
    finally:
        server.shutdown()
    assert pdf.startswith(b"%PDF")
    assert hits == []
    assert b"root:" not in pdf
