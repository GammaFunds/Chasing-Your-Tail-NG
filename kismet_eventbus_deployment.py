"""Bounded, side-effect-free deployment-time assembly for a Kismet eventbus
runtime.

This module receives all required secret values explicitly from its caller
and constructs an inactive :class:`KismetEventbusRuntime`.  It performs no
discovery, persistence, I/O, logging, network, or wall-clock operations.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import kismet_eventbus_runtime
import kismet_eventbus_runtime_config

__all__ = ("create_kismet_eventbus_runtime",)


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
