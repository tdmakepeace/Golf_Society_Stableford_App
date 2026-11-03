"""Self-signed TLS cert for local / Docker HTTPS phone testing (not for public production)."""

from __future__ import annotations

import ipaddress
import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERTS_DIR = Path(__file__).resolve().parent.parent / "certs"
CERT_PATH = CERTS_DIR / "dev-cert.pem"
KEY_PATH = CERTS_DIR / "dev-key.pem"


def lan_ipv4_addresses() -> list[str]:
    """Best-effort list of this machine's non-loopback IPv4 addresses."""
    found: set[str] = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addr = info[4][0]
            if not addr.startswith("127."):
                found.add(addr)
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            addr = sock.getsockname()[0]
            if not addr.startswith("127."):
                found.add(addr)
    except OSError:
        pass
    return sorted(found)


def extra_san_hosts() -> list[str]:
    """Optional hosts/IPs from HTTPS_EXTRA_HOSTS (comma-separated)."""
    raw = os.environ.get("HTTPS_EXTRA_HOSTS", "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def _san_name(host: str) -> x509.GeneralName | None:
    try:
        return x509.IPAddress(ipaddress.ip_address(host))
    except ValueError:
        pass
    if host:
        return x509.DNSName(host)
    return None


def ensure_dev_certificate() -> tuple[Path, Path]:
    """
    Create certs/dev-cert.pem and certs/dev-key.pem if missing.
    Includes localhost, 127.0.0.1, detected LAN IPv4 addresses, and
    any HTTPS_EXTRA_HOSTS values as subject alternative names.
    """
    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    if CERT_PATH.is_file() and KEY_PATH.is_file():
        return CERT_PATH, KEY_PATH

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Golf Society local HTTPS")]
    )
    san_names: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
    ]
    seen: set[str] = {"localhost", "127.0.0.1"}
    for addr in [*lan_ipv4_addresses(), *extra_san_hosts()]:
        if addr in seen:
            continue
        seen.add(addr)
        name = _san_name(addr)
        if name is not None:
            san_names.append(name)

    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=730))
        .add_extension(x509.SubjectAlternativeName(san_names), critical=False)
        .sign(key, hashes.SHA256())
    )

    KEY_PATH.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return CERT_PATH, KEY_PATH


def https_access_urls(port: int) -> list[str]:
    hosts = ["127.0.0.1", "localhost", *lan_ipv4_addresses(), *extra_san_hosts()]
    seen: set[str] = set()
    urls: list[str] = []
    for host in hosts:
        if host in seen:
            continue
        seen.add(host)
        urls.append(f"https://{host}:{port}")
    return urls
