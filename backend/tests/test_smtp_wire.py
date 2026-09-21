"""Runs `SmtpEmailSender` (and therefore the real `smtplib`) against a real
TCP socket served by a tiny in-process SMTP server, so the wire behaviour is
exercised - TLS upgrade, authentication, message format - instead of a
mocked `smtplib` that would only prove the mock. The TLS tests generate a
throwaway self-signed certificate with `cryptography` and are skipped where
that isn't installed.
"""

import base64
import datetime
import email
import email.policy
import ipaddress
import socket
import ssl
import threading
from pathlib import Path

import pytest

from app.services.mailer import EmailDeliveryError, SmtpEmailSender

USERNAME = "sender@example.cz"
PASSWORD = "s3cret-app-password"


class _Lines:
    """CRLF line reader over a socket that can be swapped for its TLS-wrapped
    successor mid-connection (STARTTLS)."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.buffer = b""

    def readline(self) -> bytes:
        while b"\r\n" not in self.buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("client closed")
            self.buffer += chunk
        line, _, self.buffer = self.buffer.partition(b"\r\n")
        return line

    def send(self, text: str) -> None:
        self.sock.sendall(text.encode() + b"\r\n")


class FakeSmtpServer:
    """Minimal ESMTP server: EHLO, STARTTLS, AUTH PLAIN, MAIL/RCPT/DATA,
    QUIT. Records what it received and whether each step happened over TLS.
    """

    def __init__(
        self,
        *,
        tls_context: ssl.SSLContext | None = None,
        implicit_tls: bool = False,
        offer_starttls: bool = False,
        require_auth: bool = False,
        reject_recipient: bool = False,
    ) -> None:
        self.tls_context = tls_context
        self.implicit_tls = implicit_tls
        self.offer_starttls = offer_starttls
        self.require_auth = require_auth
        self.reject_recipient = reject_recipient
        self.messages: list[bytes] = []
        self.envelopes: list[tuple[str, str]] = []
        self.auth_attempts: list[bool] = []  # one entry per AUTH, True if it came over TLS
        self.connections = 0
        self._listener = socket.socket()
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(5)
        self._listener.settimeout(0.2)
        self.port = self._listener.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._listener.close()

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._listener.accept()
            except (TimeoutError, OSError):
                continue
            self.connections += 1
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(5)
            tls = False
            if self.implicit_tls:
                conn = self.tls_context.wrap_socket(conn, server_side=True)
                tls = True
            lines = _Lines(conn)
            lines.send("220 fake.example ESMTP")
            authenticated = False
            sender = ""
            while True:
                line = lines.readline().decode()
                command = line.split(" ", 1)[0].upper()
                if command == "EHLO":
                    replies = ["250-fake.example"]
                    if self.offer_starttls and not tls:
                        replies.append("250-STARTTLS")
                    replies.append("250-AUTH PLAIN")
                    replies.append("250 8BITMIME")
                    lines.send("\r\n".join(replies))
                elif command == "STARTTLS":
                    lines.send("220 ready")
                    conn = self.tls_context.wrap_socket(conn, server_side=True)
                    lines = _Lines(conn)
                    tls = True
                elif command == "AUTH":
                    self.auth_attempts.append(tls)
                    _, user, password = base64.b64decode(line.split()[2]).split(b"\0")
                    if (user.decode(), password.decode()) == (USERNAME, PASSWORD):
                        authenticated = True
                        lines.send("235 2.7.0 Authentication successful")
                    else:
                        lines.send("535 5.7.8 Authentication credentials invalid")
                elif command == "MAIL":
                    if self.require_auth and not authenticated:
                        lines.send("530 5.7.0 Authentication required")
                    else:
                        sender = line.split("<", 1)[1].split(">", 1)[0]
                        lines.send("250 OK")
                elif command == "RCPT":
                    if self.reject_recipient:
                        lines.send("550 5.1.1 No such user")
                    else:
                        self.envelopes.append((sender, line.split("<", 1)[1].split(">", 1)[0]))
                        lines.send("250 OK")
                elif command == "DATA":
                    lines.send("354 End data with <CR><LF>.<CR><LF>")
                    data = []
                    while True:
                        data_line = lines.readline()
                        if data_line == b".":
                            break
                        data.append(data_line[1:] if data_line.startswith(b"..") else data_line)
                    self.messages.append(b"\r\n".join(data) + b"\r\n")
                    lines.send("250 OK queued")
                elif command == "QUIT":
                    lines.send("221 bye")
                    return
                else:
                    lines.send("250 OK")
        except (ConnectionError, OSError, ssl.SSLError):
            pass  # client hung up or refused our certificate - the assertions look at what was recorded
        finally:
            conn.close()

    def parse_last_message(self) -> email.message.EmailMessage:
        return email.message_from_bytes(self.messages[-1], policy=email.policy.default)


@pytest.fixture(scope="module")
def certificate(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A self-signed certificate for 127.0.0.1 - PEM with key and cert in
    one file, usable both as the server's identity and (as the trust
    anchor) as the client's `cafile`."""
    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .sign(key, hashes.SHA256())
    )
    path = tmp_path_factory.mktemp("tls") / "server.pem"
    path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        + cert.public_bytes(serialization.Encoding.PEM)
    )
    return path


@pytest.fixture()
def server_tls_context(certificate: Path) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate)
    return context


@pytest.fixture()
def trusting_client_context(certificate: Path) -> ssl.SSLContext:
    """Verifies certificates and hostnames exactly like the default context,
    but trusts the throwaway certificate above."""
    return ssl.create_default_context(cafile=str(certificate))


def _sender(server: FakeSmtpServer, *, security: str, context: ssl.SSLContext | None = None, password: str = PASSWORD):
    return SmtpEmailSender(
        "127.0.0.1",
        server.port,
        USERNAME,
        password,
        USERNAME,
        security,
        from_name="Rovis",
        ssl_context=context,
    )


@pytest.fixture()
def serve():
    servers: list[FakeSmtpServer] = []

    def _start(**kwargs) -> FakeSmtpServer:
        server = FakeSmtpServer(**kwargs)
        servers.append(server)
        return server

    yield _start
    for server in servers:
        server.close()


def test_message_is_delivered_with_correct_envelope_headers_and_both_bodies(serve) -> None:
    server = serve(require_auth=True)
    _sender(server, security="none").send_login_code("jana@example.cz", "482913", 10)

    assert server.envelopes == [(USERNAME, "jana@example.cz")]
    message = server.parse_last_message()
    assert message["To"] == "jana@example.cz"
    assert message["From"] == f"Rovis <{USERNAME}>"
    assert message["Subject"] == "Váš přihlašovací kód do Rovis"  # diacritics survive header encoding
    assert message["Date"] and message["Message-ID"].endswith("@example.cz>")
    assert message["Auto-Submitted"] == "auto-generated"

    plain = message.get_body(("plain",)).get_content()
    html_part = message.get_body(("html",)).get_content()
    assert "482913" in plain and "10 minut" in plain
    assert "482913" in html_part and "<html" in html_part


def test_starttls_upgrades_before_credentials_are_sent(serve, server_tls_context, trusting_client_context) -> None:
    server = serve(tls_context=server_tls_context, offer_starttls=True, require_auth=True)
    _sender(server, security="starttls", context=trusting_client_context).send_login_code("jana@example.cz", "111222", 10)

    assert server.auth_attempts == [True]  # the password only ever crossed an encrypted channel
    assert "111222" in server.parse_last_message().get_body(("plain",)).get_content()


def test_implicit_ssl_delivers(serve, server_tls_context, trusting_client_context) -> None:
    server = serve(tls_context=server_tls_context, implicit_tls=True, require_auth=True)
    _sender(server, security="ssl", context=trusting_client_context).send_login_code("jana@example.cz", "333444", 10)

    assert server.auth_attempts == [True]
    assert server.envelopes == [(USERNAME, "jana@example.cz")]


def test_untrusted_certificate_is_refused_and_no_credentials_are_sent(serve, server_tls_context) -> None:
    """The default context (system trust store) must reject a self-signed
    certificate: TLS verification is on, and the password never leaves."""
    server = serve(tls_context=server_tls_context, offer_starttls=True, require_auth=True)
    sender = _sender(server, security="starttls")  # no ssl_context -> production default

    with pytest.raises(EmailDeliveryError, match="SSLCertVerificationError"):
        sender.send_login_code("jana@example.cz", "555666", 10)
    assert server.auth_attempts == []
    assert server.messages == []


def test_server_that_does_not_offer_starttls_is_not_used_in_clear_text(serve) -> None:
    """`starttls` mode must not silently fall back to plaintext if the
    server doesn't offer the upgrade - smtplib raises instead."""
    server = serve(offer_starttls=False, require_auth=True)
    with pytest.raises(EmailDeliveryError):
        _sender(server, security="starttls").send_login_code("jana@example.cz", "777888", 10)
    assert server.auth_attempts == []
    assert server.messages == []


def test_wrong_password_fails_without_leaking_it(serve) -> None:
    server = serve(require_auth=True)
    with pytest.raises(EmailDeliveryError) as exc_info:
        _sender(server, security="none", password="wrong-password").send_login_code("jana@example.cz", "999000", 10)

    assert "SMTPAuthenticationError" in str(exc_info.value)
    assert "wrong-password" not in str(exc_info.value)
    assert "999000" not in str(exc_info.value)
    assert server.messages == []


def test_rejected_recipient_is_reported(serve) -> None:
    server = serve(reject_recipient=True)
    with pytest.raises(EmailDeliveryError, match="SMTPRecipientsRefused"):
        _sender(server, security="none").send_login_code("nobody@example.cz", "121212", 10)


def test_unreachable_server_is_reported() -> None:
    dead_port = socket.socket()
    dead_port.bind(("127.0.0.1", 0))
    port = dead_port.getsockname()[1]
    dead_port.close()  # nothing listens here any more

    sender = SmtpEmailSender("127.0.0.1", port, None, None, USERNAME, "none")
    with pytest.raises(EmailDeliveryError):
        sender.send_login_code("jana@example.cz", "343434", 10)
