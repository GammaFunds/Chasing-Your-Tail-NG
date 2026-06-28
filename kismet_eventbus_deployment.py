"""Bounded, side-effect-free deployment-time assembly for a Kismet eventbus
runtime.

This module receives all required secret values explicitly from its caller
and constructs an inactive :class:`KismetEventbusRuntime`.  It performs no
discovery, persistence, I/O, logging, network, or wall-clock operations.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import kismet_eventbus_runtime
import kismet_eventbus_runtime_config

__all__ = (
    "KismetEventbusDeploymentManifestV1",
    "KismetEventbusCredentialsV1",
    "create_kismet_eventbus_runtime",
    "create_kismet_eventbus_runtime_from_credential_provider",
    "create_kismet_eventbus_runtime_from_manifest",
)


@dataclass(frozen=True, slots=True)
class KismetEventbusDeploymentManifestV1:
    """Immutable, inactive, secret-free deployment manifest.

    Contains only non-secret deployment and runtime-assembly values.
    No credentials, credential references, or discovery mechanisms.
    Construction is side-effect-free.
    """

    base_url: str
    topics: tuple[str, ...]
    tls_mode: str
    connect_timeout_s: float
    reconnect_delay_s: float
    stop_join_timeout_s: float
    db_path: str | Path
    collection_session_id: str
    sensor_id: str

    def __post_init__(self) -> None:
        if type(self.base_url) is not str:
            raise TypeError("base_url")
        if type(self.topics) is not tuple:
            raise TypeError("topics")
        for topic in self.topics:
            if type(topic) is not str:
                raise TypeError("topics")
        if type(self.tls_mode) is not str:
            raise TypeError("tls_mode")
        if type(self.connect_timeout_s) is not float:
            raise TypeError("connect_timeout_s")
        if type(self.reconnect_delay_s) is not float:
            raise TypeError("reconnect_delay_s")
        if type(self.stop_join_timeout_s) is not float:
            raise TypeError("stop_join_timeout_s")
        if type(self.db_path) is not str and not isinstance(self.db_path, Path):
            raise TypeError("db_path")
        if type(self.collection_session_id) is not str:
            raise TypeError("collection_session_id")
        if type(self.sensor_id) is not str:
            raise TypeError("sensor_id")


@dataclass(frozen=True, slots=True, repr=False, eq=False, kw_only=True)
class KismetEventbusCredentialsV1:
    """Immutable, redacted deployment credentials container.

    The boundary accepts only exact built-in ``bytes`` values and does not
    expose credential content in repr or str output.
    """

    authorization_header_value: bytes
    hmac_key: bytes

    def __post_init__(self) -> None:
        if type(self.authorization_header_value) is not bytes:
            raise TypeError("authorization_header_value")
        if type(self.hmac_key) is not bytes:
            raise TypeError("hmac_key")

    def __repr__(self) -> str:
        return "<KismetEventbusCredentialsV1 redacted>"

    __str__ = __repr__


def create_kismet_eventbus_runtime(
    *,
    base_url: str,
    topics: tuple[str, ...],
    authorization_header_value: bytes,
    tls_mode: str,
    connect_timeout_s: float,
    reconnect_delay_s: float,
    stop_join_timeout_s: float,
    db_path: str | Path,
    hmac_key: bytes,
    collection_session_id: str,
    sensor_id: str,
    ingest_timestamp_us_provider: Callable[[], int],
) -> kismet_eventbus_runtime.KismetEventbusRuntime:
    """Create an inactive KismetEventbusRuntime from caller-supplied secrets.

    All arguments are keyword-only.  No I/O, no network, no wall-clock,
    no start or stop is performed.

    Returns an inactive runtime whose lifecycle is ``stopped`` and whose
    transport has not been started.
    """
    config = kismet_eventbus_runtime_config.create_kismet_eventbus_transport_config(
        base_url=base_url,
        topics=topics,
        authorization_header_value=authorization_header_value,
        tls_mode=tls_mode,
        connect_timeout_s=connect_timeout_s,
        reconnect_delay_s=reconnect_delay_s,
        stop_join_timeout_s=stop_join_timeout_s,
    )
    runtime = kismet_eventbus_runtime.KismetEventbusRuntime(
        config,
        db_path,
        hmac_key=hmac_key,
        collection_session_id=collection_session_id,
        sensor_id=sensor_id,
        ingest_timestamp_us_provider=ingest_timestamp_us_provider,
    )
    return runtime


def create_kismet_eventbus_runtime_from_credential_provider(
    *,
    manifest: KismetEventbusDeploymentManifestV1,
    credential_provider: Callable[[], KismetEventbusCredentialsV1],
    ingest_timestamp_us_provider: Callable[[], int],
) -> kismet_eventbus_runtime.KismetEventbusRuntime:
    """Create an inactive runtime from caller-owned credentials lookup.

    The wrapper itself adds no credential discovery, persistence, caching,
    logging, fallback, transformation, or runtime activation.  Provider
    behavior and lifecycle remain caller-owned.
    """
    if type(manifest) is not KismetEventbusDeploymentManifestV1:
        raise TypeError("manifest invalid")
    if not callable(credential_provider):
        raise TypeError("credential_provider invalid")

    credentials = credential_provider()
    if type(credentials) is not KismetEventbusCredentialsV1:
        raise TypeError("credentials invalid")

    return create_kismet_eventbus_runtime_from_manifest(
        manifest=manifest,
        authorization_header_value=credentials.authorization_header_value,
        hmac_key=credentials.hmac_key,
        ingest_timestamp_us_provider=ingest_timestamp_us_provider,
    )


def create_kismet_eventbus_runtime_from_manifest(
    *,
    manifest: KismetEventbusDeploymentManifestV1,
    authorization_header_value: bytes,
    hmac_key: bytes,
    ingest_timestamp_us_provider: Callable[[], int],
) -> kismet_eventbus_runtime.KismetEventbusRuntime:
    """Create an inactive KismetEventbusRuntime from a deployment manifest
    and explicit secrets.

    All arguments are keyword-only.  No I/O, no network, no wall-clock,
    no start or stop is performed.

    The manifest must not contain credentials.  The secret values are
    passed explicitly and forwarded by identity.
    """
    if type(manifest) is not KismetEventbusDeploymentManifestV1:
        raise TypeError("manifest invalid")
    return create_kismet_eventbus_runtime(
        base_url=manifest.base_url,
        topics=manifest.topics,
        authorization_header_value=authorization_header_value,
        tls_mode=manifest.tls_mode,
        connect_timeout_s=manifest.connect_timeout_s,
        reconnect_delay_s=manifest.reconnect_delay_s,
        stop_join_timeout_s=manifest.stop_join_timeout_s,
        db_path=manifest.db_path,
        hmac_key=hmac_key,
        collection_session_id=manifest.collection_session_id,
        sensor_id=manifest.sensor_id,
        ingest_timestamp_us_provider=ingest_timestamp_us_provider,
    )
