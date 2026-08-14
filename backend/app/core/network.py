"""Outbound network safety helpers.

These guards prevent Server-Side Request Forgery (SSRF): they ensure that a
user-controllable base URL cannot be pointed at loopback, link-local, private,
or cloud-metadata addresses, which could otherwise be used to probe internal
services or exfiltrate secrets.
"""

import ipaddress
import socket
from urllib.parse import urlparse

from app.core.errors import QuantError


# Loopback / private / link-local / CGNAT / documentation / cloud-metadata ranges
# must never be reachable from an outbound call. 169.254.0.0/16 includes the
# AWS/GCP/Azure metadata endpoints (169.254.169.254).
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return any(ip in network for network in _BLOCKED_NETWORKS)


def validate_outbound_host(value: str) -> str:
    """Validate a host portion is a safe public outbound destination.

    Accepts either a literal IP or a DNS hostname. For hostnames we resolve all
    A/AAAA records and reject the URL if any of them resolves to a blocked
    (internal) address, which also mitigates trivial DNS-rebinding attempts.
    Returns the hostname as given.
    """
    if not value:
        raise QuantError("VALIDATION_ERROR", "base_url host must not be empty", status_code=400)

    # Reject trailing-dot / embedded-IP tricks early where cheap.
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        addr = None

    if addr is not None:
        if addr.is_unspecified or _is_blocked_ip(addr):
            raise QuantError(
                "VALIDATION_ERROR",
                "base_url host resolves to a loopback, link-local, or private address that is not allowed for outbound calls",
                status_code=400,
            )
        return value

    # Hostname: resolve every address family and reject if any is internal.
    try:
        infos = socket.getaddrinfo(value, None)
    except socket.gaierror:
        raise QuantError(
            "VALIDATION_ERROR",
            "base_url host could not be resolved",
            status_code=400,
        )
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if _is_blocked_ip(ip):
            raise QuantError(
                "VALIDATION_ERROR",
                "base_url host resolves to a loopback, link-local, or private address that is not allowed for outbound calls",
                status_code=400,
            )
    return value


def validate_safe_outbound_url(value: str, *, allow_http: bool = False) -> str:
    """Validate that ``value`` is an absolute HTTP(S) URL pointing to a safe
    public host. Returns the normalized URL.

    ``allow_http`` should only be True in a local/development runtime; outbound
    traffic should otherwise be HTTPS-only to protect secrets in transit.
    """
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise QuantError("VALIDATION_ERROR", "base_url must be an absolute HTTP(S) URL", status_code=400)
    if parsed.scheme != "https" and not allow_http:
        raise QuantError(
            "VALIDATION_ERROR",
            "base_url must use HTTPS for outbound calls",
            status_code=400,
        )
    # Strip userinfo before host validation to avoid accidental secret-bearing URLs.
    host = parsed.hostname or ""
    validate_outbound_host(host)
    return value.rstrip("/")