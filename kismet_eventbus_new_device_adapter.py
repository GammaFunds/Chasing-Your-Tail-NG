"""Inactive, pure decoder from one Kismet NEW_DEVICE eventbus envelope
to one ObservationEventV1."""

from __future__ import annotations

import json

from observation_contract import (
    ObservationEventV1,
    ObservationProvenanceV1,
    create_observation_event,
)


NEW_DEVICE = "NEW_DEVICE"
_SOURCE_TYPE = "kismet.eventbus.new_device"
_COLLECTOR_NAME = "cyt.kismet_eventbus_new_device_adapter"
_COLLECTOR_VERSION = "1.0"
_INGEST_MODE = "live"
_SOURCE_SCHEMA_VERSION = "kismet.eventbus.new-device.v1"


class KismetEventbusNewDeviceAdapterError(ValueError):
    """Raised when a Kismet NEW_DEVICE envelope is invalid."""


def decode_kismet_new_device_envelope(
    envelope: object,
    *,
    hmac_key: bytes,
    collection_session_id: str,
    sensor_id: str,
    ingest_timestamp_us: int,
) -> ObservationEventV1:
    """Decode one Kismet NEW_DEVICE eventbus envelope to an event."""

    if type(envelope) is not dict:
        raise KismetEventbusNewDeviceAdapterError(
            "envelope must be a dict"
        )

    keys = list(envelope)
    if len(keys) != 1 or keys[0] != NEW_DEVICE:
        raise KismetEventbusNewDeviceAdapterError(
            "invalid envelope topic"
        )

    payload = envelope[NEW_DEVICE]
    if type(payload) is not dict:
        raise KismetEventbusNewDeviceAdapterError(
            "invalid payload type"
        )

    device_key = payload.get("kismet.device.base.key")
    macaddr = payload.get("kismet.device.base.macaddr")
    first_time = payload.get("kismet.device.base.first_time")

    if not isinstance(device_key, str) or not device_key:
        raise KismetEventbusNewDeviceAdapterError(
            "invalid required field"
        )

    if not isinstance(macaddr, str):
        raise KismetEventbusNewDeviceAdapterError(
            "invalid required field"
        )

    normalized_mac = macaddr.strip()

    if not normalized_mac or normalized_mac == "00:00:00:00:00:00":
        raise KismetEventbusNewDeviceAdapterError(
            "invalid required field"
        )

    if (
        isinstance(first_time, bool)
        or not isinstance(first_time, int)
        or first_time < 0
    ):
        raise KismetEventbusNewDeviceAdapterError(
            "invalid required field"
        )

    source_record_reference = json.dumps(
        [
            _SOURCE_SCHEMA_VERSION,
            device_key,
            first_time,
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )

    source_timestamp_us = first_time * 1_000_000

    try:
        provenance = ObservationProvenanceV1(
            collector_name=_COLLECTOR_NAME,
            collector_version=_COLLECTOR_VERSION,
            ingest_mode=_INGEST_MODE,
            source_schema_version=_SOURCE_SCHEMA_VERSION,
        )

        event = create_observation_event(
            hmac_key=hmac_key,
            collection_session_id=collection_session_id,
            source_type=_SOURCE_TYPE,
            sensor_id=sensor_id,
            source_timestamp_us=source_timestamp_us,
            ingest_timestamp_us=ingest_timestamp_us,
            source_record_reference=source_record_reference,
            provenance=provenance,
            device_identifier=normalized_mac,
            device_identifier_kind="mac",
        )
    except (TypeError, ValueError):
        raise KismetEventbusNewDeviceAdapterError(
            "invalid required field"
        ) from None

    return event


__all__ = [
    "KismetEventbusNewDeviceAdapterError",
    "NEW_DEVICE",
    "decode_kismet_new_device_envelope",
]
