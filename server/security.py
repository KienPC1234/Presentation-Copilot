"""Small, dependency-free access policy shared by HTTP and WebSocket handlers."""

import hmac
from urllib.parse import urlsplit


def is_loopback(host: str | None) -> bool:
    return host in ("127.0.0.1", "::1", "localhost", "testclient")


def local_host_header(host_header: str | None) -> bool:
    host = (host_header or "").lower()
    return host in ("localhost", "127.0.0.1", "[::1]") or any(
        host.startswith(name + ":") and host[len(name) + 1:].isdigit()
        for name in ("localhost", "127.0.0.1", "[::1]")
    )


def same_origin(origin: str | None, host_header: str | None) -> bool:
    if not origin:
        return True  # Native WPF clients do not send an Origin header.
    parsed = urlsplit(origin)
    return parsed.scheme in ("http", "https") and parsed.netloc.lower() == (host_header or "").lower()


def authorized(host: str | None, authorization: str | None, api_token: str,
               host_header: str | None = None) -> bool:
    if api_token:
        return hmac.compare_digest(authorization or "", "Bearer " + api_token)
    return is_loopback(host) and local_host_header(host_header)
