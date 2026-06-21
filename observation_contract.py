"""Immutable, source-neutral observation contract version 1.0."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import re
from typing import Optional


SCHEMA_VERSION_V1 = "1.0"
OBSERVATION_RECORD_KIND = "observation_event"
LOCATION_LINK_RECORD_KIND = "observation_location_link"

_SOURCE_TYPE_RE = re.compile(
    r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$"
)
_OBSERVATION_ID_RE = re.compile(r"^obs_v1_[0-9a-f]{64}$")
_LOCATION_LINK_ID_RE = re.compile(r"^loc_v1_[0-9a-f]{64}$")

_DUPLICATE = "duplicate"
_IDENTITY_CONFLICT = "identity_conflict"


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")

    if not value or value != value.strip():
        raise ValueError(
            f"{name} must be a non-empty canonical string"
        )

    return value


def _require_source_type(value: object) -> str:
    source_type = _require_text("source_type", value)

    if _SOURCE_TYPE_RE.fullmatch(source_type) is None:
        raise ValueError(
            "source_type must be a lowercase namespaced value"
        )

    return source_type


def _require_timestamp_us(name: str, value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise ValueError(
            f"{name} must be a non-negative integer Unix timestamp "
            "in microseconds"
        )

    return value


def _require_signed_integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")

    return value


def _require_finite_number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")

    try:
        normalized = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be a finite number") from exc

    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be a finite number")

    return normalized


def _require_hmac_key(hmac_key: object) -> bytes:
    if not isinstance(hmac_key, bytes) or not hmac_key:
        raise ValueError("hmac_key must be non-empty bytes")

    return hmac_key


def _canonical_identity_bytes(parts: tuple[str, ...]) -> bytes:
    return json.dumps(
        list(parts),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _derive_hmac_identifier(
    prefix: str,
    hmac_key: bytes,
    parts: tuple[str, ...],
) -> str:
    digest = hmac.new(
        _require_hmac_key(hmac_key),
        _canonical_identity_bytes(parts),
        hashlib.sha256,
    ).hexdigest()

    return f"{prefix}{digest}"


@dataclass(frozen=True)
class ObservationProvenanceV1:
    """Non-secret provenance for one collected source record."""

    collector_name: str
    collector_version: str
    ingest_mode: str
    source_schema_version: Optional[str] = None

    def __post_init__(self) -> None:
        _require_text("collector_name", self.collector_name)
        _require_text("collector_version", self.collector_version)

        if self.ingest_mode not in {"live", "replay", "import"}:
            raise ValueError(
                "ingest_mode must be live, replay, or import"
            )

        if self.source_schema_version is not None:
            _require_text(
                "source_schema_version",
                self.source_schema_version,
            )


@dataclass(frozen=True)
class ObservationEventV1:
    """Immutable source event independent of later analysis."""

    schema_version: str
    record_kind: str
    observation_id: str
    collection_session_id: str
    source_type: str
    sensor_id: str
    source_timestamp_us: int
    ingest_timestamp_us: int
    source_record_reference: str
    provenance: ObservationProvenanceV1
    device_identifier: Optional[str] = None
    device_identifier_kind: Optional[str] = None
    signal_strength: Optional[float] = None
    signal_strength_unit: Optional[str] = None

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION_V1:
            raise ValueError('schema_version must be exactly "1.0"')

        if self.record_kind != OBSERVATION_RECORD_KIND:
            raise ValueError(
                'record_kind must be exactly "observation_event"'
            )

        if _OBSERVATION_ID_RE.fullmatch(self.observation_id) is None:
            raise ValueError("invalid observation_id")

        _require_text(
            "collection_session_id",
            self.collection_session_id,
        )
        _require_source_type(self.source_type)
        _require_text("sensor_id", self.sensor_id)
        _require_timestamp_us(
            "source_timestamp_us",
            self.source_timestamp_us,
        )
        _require_timestamp_us(
            "ingest_timestamp_us",
            self.ingest_timestamp_us,
        )
        _require_text(
            "source_record_reference",
            self.source_record_reference,
        )

        if not isinstance(
            self.provenance,
            ObservationProvenanceV1,
        ):
            raise ValueError(
                "provenance must be ObservationProvenanceV1"
            )

        device_values = (
            self.device_identifier,
            self.device_identifier_kind,
        )

        if (device_values[0] is None) != (device_values[1] is None):
            raise ValueError(
                "device_identifier and device_identifier_kind "
                "must both be set or both be null"
            )

        if self.device_identifier is not None:
            _require_text(
                "device_identifier",
                self.device_identifier,
            )
            _require_text(
                "device_identifier_kind",
                self.device_identifier_kind,
            )

        signal_values = (
            self.signal_strength,
            self.signal_strength_unit,
        )

        if (signal_values[0] is None) != (signal_values[1] is None):
            raise ValueError(
                "signal_strength and signal_strength_unit "
                "must both be set or both be null"
            )

        if self.signal_strength is not None:
            _require_finite_number(
                "signal_strength",
                self.signal_strength,
            )
            _require_text(
                "signal_strength_unit",
                self.signal_strength_unit,
            )


@dataclass(frozen=True)
class ObservationLocationLinkV1:
    """Immutable versioned correlation between an event and GPS fix."""

    schema_version: str
    record_kind: str
    location_link_id: str
    observation_id: str
    operator_fix_id: str
    operator_latitude: float
    operator_longitude: float
    operator_fix_timestamp_us: int
    source_to_fix_delta_us: int
    correlation_method: str
    correlation_version: str
    operator_location_accuracy_m: Optional[float] = None

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION_V1:
            raise ValueError('schema_version must be exactly "1.0"')

        if self.record_kind != LOCATION_LINK_RECORD_KIND:
            raise ValueError(
                "record_kind must be exactly "
                '"observation_location_link"'
            )

        if _LOCATION_LINK_ID_RE.fullmatch(
            self.location_link_id
        ) is None:
            raise ValueError("invalid location_link_id")

        if _OBSERVATION_ID_RE.fullmatch(self.observation_id) is None:
            raise ValueError("invalid observation_id")

        _require_text("operator_fix_id", self.operator_fix_id)

        latitude = _require_finite_number(
            "operator_latitude",
            self.operator_latitude,
        )
        longitude = _require_finite_number(
            "operator_longitude",
            self.operator_longitude,
        )

        if not -90.0 <= latitude <= 90.0:
            raise ValueError(
                "operator_latitude must be between -90 and 90"
            )

        if not -180.0 <= longitude <= 180.0:
            raise ValueError(
                "operator_longitude must be between -180 and 180"
            )

        _require_timestamp_us(
            "operator_fix_timestamp_us",
            self.operator_fix_timestamp_us,
        )
        _require_signed_integer(
            "source_to_fix_delta_us",
            self.source_to_fix_delta_us,
        )
        _require_text(
            "correlation_method",
            self.correlation_method,
        )
        _require_text(
            "correlation_version",
            self.correlation_version,
        )

        if self.operator_location_accuracy_m is not None:
            accuracy = _require_finite_number(
                "operator_location_accuracy_m",
                self.operator_location_accuracy_m,
            )

            if accuracy < 0:
                raise ValueError(
                    "operator_location_accuracy_m must be >= 0"
                )


def create_observation_event(
    *,
    hmac_key: bytes,
    collection_session_id: str,
    source_type: str,
    sensor_id: str,
    source_timestamp_us: int,
    ingest_timestamp_us: int,
    source_record_reference: str,
    provenance: ObservationProvenanceV1,
    device_identifier: Optional[str] = None,
    device_identifier_kind: Optional[str] = None,
    signal_strength: Optional[float] = None,
    signal_strength_unit: Optional[str] = None,
) -> ObservationEventV1:
    """Create an event with a deterministic local HMAC identity."""

    normalized_source_type = _require_source_type(source_type)
    normalized_sensor_id = _require_text("sensor_id", sensor_id)
    normalized_session_id = _require_text(
        "collection_session_id",
        collection_session_id,
    )
    normalized_reference = _require_text(
        "source_record_reference",
        source_record_reference,
    )

    observation_id = _derive_hmac_identifier(
        "obs_v1_",
        hmac_key,
        (
            normalized_source_type,
            normalized_sensor_id,
            normalized_session_id,
            normalized_reference,
        ),
    )

    return ObservationEventV1(
        schema_version=SCHEMA_VERSION_V1,
        record_kind=OBSERVATION_RECORD_KIND,
        observation_id=observation_id,
        collection_session_id=normalized_session_id,
        source_type=normalized_source_type,
        sensor_id=normalized_sensor_id,
        source_timestamp_us=source_timestamp_us,
        ingest_timestamp_us=ingest_timestamp_us,
        source_record_reference=normalized_reference,
        provenance=provenance,
        device_identifier=device_identifier,
        device_identifier_kind=device_identifier_kind,
        signal_strength=signal_strength,
        signal_strength_unit=signal_strength_unit,
    )


def create_observation_location_link(
    *,
    hmac_key: bytes,
    observation: ObservationEventV1,
    operator_fix_id: str,
    operator_latitude: float,
    operator_longitude: float,
    operator_fix_timestamp_us: int,
    correlation_method: str = "nearest_fix_bounded",
    correlation_version: str = "1.0",
    operator_location_accuracy_m: Optional[float] = None,
) -> ObservationLocationLinkV1:
    """Create a deterministic versioned location-correlation link."""

    if not isinstance(observation, ObservationEventV1):
        raise ValueError(
            "observation must be ObservationEventV1"
        )

    normalized_fix_id = _require_text(
        "operator_fix_id",
        operator_fix_id,
    )
    normalized_method = _require_text(
        "correlation_method",
        correlation_method,
    )
    normalized_version = _require_text(
        "correlation_version",
        correlation_version,
    )
    normalized_fix_timestamp = _require_timestamp_us(
        "operator_fix_timestamp_us",
        operator_fix_timestamp_us,
    )

    location_link_id = _derive_hmac_identifier(
        "loc_v1_",
        hmac_key,
        (
            observation.observation_id,
            normalized_fix_id,
            normalized_method,
            normalized_version,
        ),
    )

    return ObservationLocationLinkV1(
        schema_version=SCHEMA_VERSION_V1,
        record_kind=LOCATION_LINK_RECORD_KIND,
        location_link_id=location_link_id,
        observation_id=observation.observation_id,
        operator_fix_id=normalized_fix_id,
        operator_latitude=operator_latitude,
        operator_longitude=operator_longitude,
        operator_fix_timestamp_us=normalized_fix_timestamp,
        source_to_fix_delta_us=(
            normalized_fix_timestamp
            - observation.source_timestamp_us
        ),
        correlation_method=normalized_method,
        correlation_version=normalized_version,
        operator_location_accuracy_m=(
            operator_location_accuracy_m
        ),
    )


def compare_observation_source_facts(
    existing: ObservationEventV1,
    incoming: ObservationEventV1,
) -> str:
    """Return duplicate or identity_conflict for two event records."""

    if not isinstance(existing, ObservationEventV1):
        raise ValueError("existing must be ObservationEventV1")

    if not isinstance(incoming, ObservationEventV1):
        raise ValueError("incoming must be ObservationEventV1")

    if existing.observation_id != incoming.observation_id:
        return _IDENTITY_CONFLICT

    fields = (
        "source_type",
        "sensor_id",
        "collection_session_id",
        "source_record_reference",
        "device_identifier",
        "device_identifier_kind",
        "source_timestamp_us",
        "signal_strength",
        "signal_strength_unit",
    )

    existing_facts = tuple(
        getattr(existing, field)
        for field in fields
    )
    incoming_facts = tuple(
        getattr(incoming, field)
        for field in fields
    )

    if existing_facts == incoming_facts:
        return _DUPLICATE

    return _IDENTITY_CONFLICT


__all__ = [
    "ObservationEventV1",
    "ObservationLocationLinkV1",
    "ObservationProvenanceV1",
    "compare_observation_source_facts",
    "create_observation_event",
    "create_observation_location_link",
]
