from collections.abc import Callable
from pathlib import Path

from kismet_eventbus_new_device_adapter import (
    KismetEventbusNewDeviceAdapterError,
    decode_kismet_new_device_envelope,
)
from observation_store import ObservationStore


class KismetEventbusObservationHandler:
    def __init__(
        self,
        db_path: str | Path,
        *,
        hmac_key: bytes,
        collection_session_id: str,
        sensor_id: str,
        ingest_timestamp_us_provider: Callable[[], int],
    ) -> None:
        self._db_path = self._require_db_path(db_path)
        self._hmac_key = self._require_hmac_key(hmac_key)
        self._collection_session_id = self._require_text(
            "collection_session_id",
            collection_session_id,
        )
        self._sensor_id = self._require_text("sensor_id", sensor_id)
        self._ingest_timestamp_us_provider = (
            self._require_ingest_timestamp_us_provider(
                ingest_timestamp_us_provider,
            )
        )

    def __call__(
        self,
        envelope: dict[str, object],
    ) -> str:
        ingest_timestamp_us = self._ingest_timestamp_us_provider()
        if type(ingest_timestamp_us) is not int or ingest_timestamp_us < 0:
            raise ValueError("ingest_timestamp_us")

        try:
            event = decode_kismet_new_device_envelope(
                envelope,
                hmac_key=self._hmac_key,
                collection_session_id=self._collection_session_id,
                sensor_id=self._sensor_id,
                ingest_timestamp_us=ingest_timestamp_us,
            )
        except KismetEventbusNewDeviceAdapterError:
            return "malformed"

        with ObservationStore(self._db_path) as store:
            return store.insert_observation_event(event)

    @staticmethod
    def _require_db_path(db_path: str | Path) -> Path:
        if type(db_path) is str:
            if not db_path:
                raise ValueError("db_path")
            return Path(db_path)

        if isinstance(db_path, Path):
            return Path(db_path)

        raise ValueError("db_path")

    @staticmethod
    def _require_hmac_key(hmac_key: bytes) -> bytes:
        if type(hmac_key) is not bytes or not hmac_key:
            raise ValueError("hmac_key")
        return hmac_key

    @staticmethod
    def _require_text(name: str, value: str) -> str:
        if type(value) is not str or not value or value.strip() != value:
            raise ValueError(name)
        return value

    @staticmethod
    def _require_ingest_timestamp_us_provider(
        ingest_timestamp_us_provider: Callable[[], int],
    ) -> Callable[[], int]:
        if not callable(ingest_timestamp_us_provider):
            raise ValueError("ingest_timestamp_us_provider")
        return ingest_timestamp_us_provider


__all__ = ["KismetEventbusObservationHandler"]
