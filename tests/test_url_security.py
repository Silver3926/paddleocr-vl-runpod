import socket

import pytest

from url_security import validate_remote_url


def fake_public_dns(*args, **kwargs):
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
    ]


def fake_private_dns(*args, **kwargs):
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443))
    ]


def test_requires_https():
    with pytest.raises(ValueError, match="HTTPS"):
        validate_remote_url("http://example.com/file.pdf")


def test_rejects_credentials():
    with pytest.raises(ValueError, match="credentials"):
        validate_remote_url("https://user:password@example.com/file.pdf")


def test_rejects_localhost():
    with pytest.raises(ValueError, match="hostname"):
        validate_remote_url("https://localhost/file.pdf")


def test_rejects_metadata_ip():
    with pytest.raises(ValueError):
        validate_remote_url("https://169.254.169.254/latest/meta-data")


def test_rejects_private_dns_result(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", fake_private_dns)

    with pytest.raises(ValueError, match="private"):
        validate_remote_url("https://example.com/file.pdf")


def test_accepts_public_https_url(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", fake_public_dns)

    assert validate_remote_url("https://example.com/file.pdf") == (
        "https://example.com/file.pdf"
    )


def test_rejects_non_standard_port(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", fake_public_dns)

    with pytest.raises(ValueError, match="port"):
        validate_remote_url("https://example.com:8443/file.pdf")
