"""Browser navigation safety policy."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.core import get_settings


class BrowserPolicyError(Exception):
    """Raised when a browser target violates the configured policy."""


@dataclass(frozen=True)
class ValidatedUrl:
    url: str
    scheme: str
    hostname: str
    origin: str


def _allowed_domains() -> set[str]:
    return {
        domain.strip().lower().rstrip(".")
        for domain in get_settings().BROWSER_ALLOWED_DOMAINS.split(",")
        if domain.strip()
    }


def _allowed_schemes() -> set[str]:
    return {
        scheme.strip().lower().rstrip(":")
        for scheme in get_settings().BROWSER_ALLOWED_SCHEMES.split(",")
        if scheme.strip()
    }


def _is_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


def _reject_private_target(hostname: str) -> None:
    if not _is_ip_literal(hostname):
        return
    address = ipaddress.ip_address(hostname)
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
        raise BrowserPolicyError("Private, loopback, link-local, and reserved IP targets are blocked.")
    raise BrowserPolicyError("IP-literal browser targets are not allowed; use an explicit domain.")


def _validate_parts(parts: SplitResult) -> tuple[str, str, str]:
    if not parts.scheme or parts.scheme.lower() not in _allowed_schemes():
        raise BrowserPolicyError("URL scheme is not allowed by browser policy.")
    if parts.username or parts.password:
        raise BrowserPolicyError("URLs containing embedded credentials are not allowed.")
    if not parts.hostname:
        raise BrowserPolicyError("URL must include a hostname.")
    hostname = parts.hostname.lower().rstrip(".")
    _reject_private_target(hostname)
    domains = _allowed_domains()
    if not domains:
        raise BrowserPolicyError("Browser navigation is disabled until BROWSER_ALLOWED_DOMAINS is configured.")
    if hostname not in domains:
        raise BrowserPolicyError(f"Browser domain is not allowlisted: {hostname}")
    if parts.port is not None:
        expected_port = 443 if parts.scheme.lower() == "https" else 80
        if parts.port != expected_port:
            raise BrowserPolicyError("Non-standard browser ports are not allowed.")
    return parts.scheme.lower(), hostname, parts.path or "/"


def validate_url(raw_url: str) -> ValidatedUrl:
    """Validate and normalize a user-supplied browser URL."""
    if not get_settings().BROWSER_ENABLED:
        raise BrowserPolicyError("Browser foundation is disabled.")
    if not raw_url or len(raw_url) > 2048:
        raise BrowserPolicyError("Browser URL is missing or exceeds the length limit.")
    parts = urlsplit(raw_url.strip())
    scheme, hostname, _path = _validate_parts(parts)
    normalized = urlunsplit((scheme, parts.netloc.lower(), parts.path or "/", parts.query, ""))
    origin = f"{scheme}://{hostname}"
    if parts.port is not None:
        origin += f":{parts.port}"
    return ValidatedUrl(url=normalized, scheme=scheme, hostname=hostname, origin=origin)


def validate_final_url(raw_url: str, expected_origin: str) -> ValidatedUrl:
    """Validate a final URL after navigation and reject cross-origin redirects."""
    result = validate_url(raw_url)
    if result.origin != expected_origin:
        raise BrowserPolicyError("Navigation redirected to a different origin and was blocked.")
    return result
