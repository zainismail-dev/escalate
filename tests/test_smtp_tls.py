"""Review #5: SMTP used smtplib's default TLS context, which checks neither the certificate nor
the hostname. A server with a self-signed certificate must now be refused (SSL and STARTTLS)."""

import datetime as dt
import socket
import ssl
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from escalate.channels import email_smtp


def _self_signed(tmp: Path) -> tuple[Path, Path]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp / "cert.pem", tmp / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


class FakeTlsSmtp:
    """A one-connection SMTP server with a self-signed certificate (implicit TLS or STARTTLS)."""

    def __init__(self, cert: Path, key: Path, starttls: bool) -> None:
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(cert, key)
        self.starttls = starttls
        self.sock = socket.create_server(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        try:
            conn, _ = self.sock.accept()
            if self.starttls:
                f = conn.makefile("rb")
                conn.sendall(b"220 fake ESMTP\r\n")
                f.readline()  # EHLO
                conn.sendall(b"250-fake\r\n250 STARTTLS\r\n")
                f.readline()  # STARTTLS
                conn.sendall(b"220 go ahead\r\n")
            tls = self.ctx.wrap_socket(conn, server_side=True)
            tls.sendall(b"220 fake ESMTP\r\n")
            tls.recv(1024)
            tls.close()
        except (OSError, ssl.SSLError):
            pass  # the client refused our certificate: that's the point
        finally:
            self.sock.close()


@pytest.fixture
def certs(tmp_path: Path) -> Iterator[tuple[Path, Path]]:
    yield _self_signed(tmp_path)


@pytest.mark.parametrize(("starttls", "port_for"), [(False, 465), (True, 587)])
def test_self_signed_smtp_server_is_refused(
    certs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, starttls: bool, port_for: int
) -> None:
    server = FakeTlsSmtp(*certs, starttls=starttls)
    # _ssl_factory picks SSL for port 465 and STARTTLS otherwise; send it to the fake's port.
    # (Patch only that class: SMTP_SSL.__init__ itself calls smtplib.SMTP.__init__.)
    name = "SMTP" if starttls else "SMTP_SSL"
    real = getattr(email_smtp.smtplib, name)
    monkeypatch.setattr(email_smtp.smtplib, name, lambda h, p, **kw: real(h, server.port, **kw))
    with pytest.raises(ssl.SSLCertVerificationError):
        email_smtp._ssl_factory("localhost", port_for)


def test_trusted_certificate_still_connects(
    certs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive control: the same server is accepted once its certificate is trusted, so the
    refusal above really comes from certificate verification."""
    cert, _ = certs
    server = FakeTlsSmtp(*certs, starttls=False)
    monkeypatch.setattr(email_smtp, "tls_context", lambda: ssl.create_default_context(cafile=cert))
    smtp = email_smtp.smtplib.SMTP_SSL("localhost", server.port, context=email_smtp.tls_context())
    assert smtp.sock is not None
    smtp.close()


def test_default_context_verifies() -> None:
    ctx = email_smtp.tls_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
