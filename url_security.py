import ipaddress
import socket
from urllib.parse import urlparse


BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
}

ALLOWED_SCHEMES = {"https"}
ALLOWED_PORTS = {443, None}


def _is_blocked_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)

    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def validate_remote_url(url: str) -> str:
    """Validate a remote URL before the worker makes an outbound request."""
    if not isinstance(url, str):
        raise ValueError("Input URL must be a string.")

    value = url.strip()
    if not value:
        raise ValueError("Input URL must not be empty.")

    parsed = urlparse(value)

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError("Input URL must use HTTPS.")
    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not allowed.")
    if not parsed.hostname:
        raise ValueError("Input URL must contain a valid host.")
    if parsed.port not in ALLOWED_PORTS:
        raise ValueError("Only HTTPS port 443 is allowed.")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in BLOCKED_HOSTNAMES:
        raise ValueError("Input URL hostname is not allowed.")

    try:
        addresses = socket.getaddrinfo(
            hostname,
            parsed.port or 443,
            type=socket.SOCK_STREAM,
        )
    except (socket.gaierror, UnicodeError) as exc:
        raise ValueError("Unable to resolve input URL hostname.") from exc

    if not addresses:
        raise ValueError("Input URL hostname has no address.")

    for address in addresses:
        ip = address[4][0]
        if _is_blocked_ip(ip):
            raise ValueError(
                "Input URL resolves to a private or reserved IP address."
            )

    return value
