"""Immutable, side-effect-free transport configuration boundary.

This module provides a validated configuration object for
KismetEventbusTransport.  It performs no I/O, env access, or home-
directory lookups.  Every value is validated at construction time by
the factory function.
"""

from __future__ import annotations

import ipaddress
import math
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

__all__ = [
    "KismetEventbusTransportConfigV1",
    "create_kismet_eventbus_transport_config",
]


class KismetEventbusTransportConfigError(ValueError):
    """Raised on invalid configuration values.

    Instances must never contain the authorization value or a full URL
    with embedded credentials.
    """


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

_TLS_MODES = frozenset({"verify_required", "loopback_plaintext"})

_HTTP_SCHEMES = frozenset({"http", "https"})


def _is_ipv4_loopback(host: str) -> bool:
    """True when *host* is an IPv4 address in 127.0.0.0/8."""
    try:
        addr = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        return False
    return addr in ipaddress.IPv4Network("127.0.0.0/8")


def _is_ipv6_loopback(host: str) -> bool:
    """True when *host* is the IPv6 loopback ``::1``."""
    try:
        addr = ipaddress.IPv6Address(host)
    except ipaddress.AddressValueError:
        return False
    return addr == ipaddress.IPv6Address("::1")


def _is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    if _is_ipv4_loopback(host):
        return True
    if _is_ipv6_loopback(host):
        return True
    return False


def _validate_tls_mode(tls_mode: Any) -> str:
    if type(tls_mode) is not str:
        raise KismetEventbusTransportConfigError("tls_mode invalid")
    if tls_mode not in _TLS_MODES:
        raise KismetEventbusTransportConfigError("tls_mode invalid")
    return tls_mode


def _validate_base_url(
    base_url: Any,
    tls_mode: str,
) -> str:
    if type(base_url) is not str:
        raise KismetEventbusTransportConfigError("base_url invalid")

    if any(
        ord(character) <= 0x20
        or ord(character) == 0x7F
        for character in base_url
    ):
        raise KismetEventbusTransportConfigError(
            "base_url invalid"
        )

    if base_url.startswith("https://"):
        scheme = "https"
    elif base_url.startswith("http://"):
        scheme = "http"
    else:
        raise KismetEventbusTransportConfigError(
            "base_url scheme invalid"
        )

    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except ValueError:
        raise KismetEventbusTransportConfigError(
            "base_url invalid"
        ) from None

    if parsed.scheme != scheme:
        raise KismetEventbusTransportConfigError(
            "base_url scheme invalid"
        )

    host = parsed.hostname
    if host is None or host == "":
        raise KismetEventbusTransportConfigError(
            "base_url host invalid"
        )

    if parsed.username is not None or parsed.password is not None:
        raise KismetEventbusTransportConfigError(
            "base_url credentials invalid"
        )

    if "?" in base_url:
        raise KismetEventbusTransportConfigError(
            "base_url query invalid"
        )

    if "#" in base_url:
        raise KismetEventbusTransportConfigError(
            "base_url fragment invalid"
        )

    if ";" in parsed.netloc or ";" in parsed.path:
        raise KismetEventbusTransportConfigError(
            "base_url path invalid"
        )

    path = parsed.path
    if path not in {"", "/"}:
        raise KismetEventbusTransportConfigError(
            "base_url path invalid"
        )

    if parsed.netloc.endswith(":"):
        raise KismetEventbusTransportConfigError(
            "base_url port invalid"
        )

    if port is not None and not (1 <= port <= 65535):
        raise KismetEventbusTransportConfigError(
            "base_url port invalid"
        )

    if scheme == "https":
        if tls_mode != "verify_required":
            raise KismetEventbusTransportConfigError(
                "base_url tls mismatch"
            )
    else:
        if tls_mode != "loopback_plaintext":
            raise KismetEventbusTransportConfigError(
                "base_url tls mismatch"
            )
        if host == "localhost" and not (
            parsed.netloc == "localhost"
            or parsed.netloc.startswith("localhost:")
        ):
            raise KismetEventbusTransportConfigError(
                "base_url loopback invalid"
            )

        if not _is_loopback_host(host):
            raise KismetEventbusTransportConfigError(
                "base_url loopback invalid"
            )

    if path == "/":
        return base_url[:-1]

    return base_url


def _validate_topics(
    topics: Any,
) -> tuple[str, ...]:
    if type(topics) is not tuple:
        raise KismetEventbusTransportConfigError("topics invalid")

    if len(topics) == 0:
        raise KismetEventbusTransportConfigError("topics empty")

    seen: set[str] = set()
    result: list[str] = []

    for topic in topics:
        if type(topic) is not str:
            raise KismetEventbusTransportConfigError("topic invalid")
        if topic == "":
            raise KismetEventbusTransportConfigError("topic empty")
        if topic != topic.strip():
            raise KismetEventbusTransportConfigError("topic whitespace")

        if topic not in seen:
            seen.add(topic)
            result.append(topic)

    return tuple(result)


def _validate_authorization_header_value(
    raw: Any,
) -> bytes:
    if type(raw) is not bytes:
        raise KismetEventbusTransportConfigError("authorization invalid")
    if len(raw) == 0:
        raise KismetEventbusTransportConfigError("authorization empty")

    try:
        decoded = raw.decode("ascii")
    except UnicodeDecodeError:
        raise KismetEventbusTransportConfigError("authorization not ascii")

    if "\r" in decoded or "\n" in decoded:
        raise KismetEventbusTransportConfigError("authorization line break")

    return raw


def _validate_time_value(
    raw: Any,
    name: str,
) -> float:
    if type(raw) not in (int, float):
        raise KismetEventbusTransportConfigError(f"{name} invalid")

    value = float(raw)

    if math.isnan(value) or math.isinf(value):
        raise KismetEventbusTransportConfigError(f"{name} invalid")

    if value <= 0:
        raise KismetEventbusTransportConfigError(f"{name} invalid")

    return value


# ------------------------------------------------------------------
# Public config class  (frozen, no secret in repr/str/eq)
# ------------------------------------------------------------------


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class KismetEventbusTransportConfigV1:
    """Immutable, validated configuration for KismetEventbusTransport.

    Public properties expose only non-secret fields.  The authorization
    header value is never exposed through repr, str, equality, or any
    public property.
    """

    _base_url: str
    _topics: tuple[str, ...]
    _authorization_header_value: bytes
    _tls_mode: str
    _connect_timeout_s: float
    _reconnect_delay_s: float
    _stop_join_timeout_s: float

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"base_url={self._base_url!r}, "
            f"topics={self._topics!r}, "
            f"authorization_header_value=<redacted>, "
            f"tls_mode={self._tls_mode!r}, "
            f"connect_timeout_s={self._connect_timeout_s!r}, "
            f"reconnect_delay_s={self._reconnect_delay_s!r}, "
            f"stop_join_timeout_s={self._stop_join_timeout_s!r})"
        )

    def __str__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"base_url={self._base_url!r}, "
            f"topics={self._topics!r}, "
            f"authorization_header_value=<redacted>, "
            f"tls_mode={self._tls_mode!r}, "
            f"connect_timeout_s={self._connect_timeout_s!r}, "
            f"reconnect_delay_s={self._reconnect_delay_s!r}, "
            f"stop_join_timeout_s={self._stop_join_timeout_s!r})"
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def topics(self) -> tuple[str, ...]:
        return self._topics

    @property
    def tls_mode(self) -> str:
        return self._tls_mode

    @property
    def connect_timeout_s(self) -> float:
        return self._connect_timeout_s

    @property
    def reconnect_delay_s(self) -> float:
        return self._reconnect_delay_s

    @property
    def stop_join_timeout_s(self) -> float:
        return self._stop_join_timeout_s


# ------------------------------------------------------------------
# Public factory
# ------------------------------------------------------------------


def create_kismet_eventbus_transport_config(
    *,
    base_url: str,
    topics: tuple[str, ...],
    authorization_header_value: bytes,
    tls_mode: str,
    connect_timeout_s: float,
    reconnect_delay_s: float,
    stop_join_timeout_s: float,
) -> KismetEventbusTransportConfigV1:
    """Create an immutable validated transport config.

    All arguments are keyword-only.  No I/O is performed.  The returned
    config is guaranteed to hold only valid values.
    """
    validated_tls_mode = _validate_tls_mode(tls_mode)
    validated_base_url = _validate_base_url(base_url, validated_tls_mode)
    validated_topics = _validate_topics(topics)
    validated_auth = _validate_authorization_header_value(
        authorization_header_value
    )

    validated_connect = _validate_time_value(
        connect_timeout_s, "connect_timeout_s"
    )
    validated_reconnect = _validate_time_value(
        reconnect_delay_s, "reconnect_delay_s"
    )
    validated_stop_join = _validate_time_value(
        stop_join_timeout_s, "stop_join_timeout_s"
    )

    return KismetEventbusTransportConfigV1(
        _base_url=validated_base_url,
        _topics=validated_topics,
        _authorization_header_value=validated_auth,
        _tls_mode=validated_tls_mode,
        _connect_timeout_s=validated_connect,
        _reconnect_delay_s=validated_reconnect,
        _stop_join_timeout_s=validated_stop_join,
    )
