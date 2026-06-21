from contextlib import closing
from dataclasses import FrozenInstanceError, fields
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from observation_store import ObservationStore
from synthetic_jsonl_adapter import (
    ReplaySummaryV1,
    SyntheticJsonlDecodeError,
    decode_synthetic_jsonl,
    replay_synthetic_jsonl,
)


class SyntheticJsonlAdapterTests(unittest.TestCase):
    KEY = b"synthetic-jsonl-test-key"

    @staticmethod
    def record(
        *,
        source_record_reference="record_alpha",
        source_timestamp_us=1_000_000,
        **optional,
    ):
        value = {
            "source_record_reference": source_record_reference,
            "source_timestamp_us": source_timestamp_us,
        }
        value.update(optional)
        return value

    def line(self, **values):
        return json.dumps(
            self.record(**values),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )

    def open_store(self):
        tempdir = tempfile.TemporaryDirectory()
        path = Path(tempdir.name) / "observations.sqlite"
        store = ObservationStore(path)

        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        return store, path

    def decode(self, lines, **overrides):
        values = {
            "hmac_key": self.KEY,
            "collection_session_id": "collection_alpha",
            "sensor_id": "sensor_alpha",
            "ingest_timestamp_us": 1_000_500,
        }
        values.update(overrides)
        return decode_synthetic_jsonl(lines, **values)

    def replay(self, lines, store, **overrides):
        values = {
            "store": store,
            "hmac_key": self.KEY,
            "collection_session_id": "collection_alpha",
            "sensor_id": "sensor_alpha",
            "ingest_timestamp_us": 1_000_500,
        }
        values.update(overrides)
        return replay_synthetic_jsonl(lines, **values)

    @staticmethod
    def stored_event_count(path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM observation_events"
            ).fetchone()[0]

    def test_decode_valid_single_and_multiple_records(self):
        single = self.decode([self.line()])
        self.assertEqual(len(single), 1)
        self.assertEqual(
            single[0].source_record_reference,
            "record_alpha",
        )

        multiple = self.decode(
            [
                self.line(
                    source_record_reference="record_alpha"
                ),
                self.line(
                    source_record_reference="record_beta",
                    source_timestamp_us=2_000_000,
                ),
            ]
        )

        self.assertEqual(len(multiple), 2)
        self.assertEqual(
            [
                event.source_record_reference
                for event in multiple
            ],
            ["record_alpha", "record_beta"],
        )

    def test_adapter_controls_source_and_provenance(self):
        event = self.decode(
            [
                self.line(
                    device_identifier="device_alpha",
                    device_identifier_kind="synthetic_id",
                    signal_strength=-42,
                    signal_strength_unit="synthetic_unit",
                )
            ],
            collection_session_id="collection_beta",
            sensor_id="sensor_beta",
            ingest_timestamp_us=9_000_000,
        )[0]

        self.assertEqual(event.source_type, "synthetic.jsonl")
        self.assertEqual(
            event.collection_session_id,
            "collection_beta",
        )
        self.assertEqual(event.sensor_id, "sensor_beta")
        self.assertEqual(
            event.ingest_timestamp_us,
            9_000_000,
        )
        self.assertEqual(
            event.provenance.collector_name,
            "cyt.synthetic_jsonl_adapter",
        )
        self.assertEqual(
            event.provenance.collector_version,
            "1.0",
        )
        self.assertEqual(
            event.provenance.ingest_mode,
            "replay",
        )
        self.assertEqual(
            event.provenance.source_schema_version,
            "cyt.synthetic-jsonl.v1",
        )

    def test_replay_insert_then_duplicate_counts(self):
        store, _ = self.open_store()
        lines = [
            self.line(
                source_record_reference="record_alpha"
            ),
            self.line(
                source_record_reference="record_beta",
                source_timestamp_us=2_000_000,
            ),
        ]

        first = self.replay(lines, store)
        second = self.replay(lines, store)

        self.assertEqual(
            first,
            ReplaySummaryV1(
                total_records=2,
                inserted=2,
                duplicate=0,
                identity_conflict=0,
            ),
        )
        self.assertEqual(
            second,
            ReplaySummaryV1(
                total_records=2,
                inserted=0,
                duplicate=2,
                identity_conflict=0,
            ),
        )

    def test_same_identity_changed_source_facts_counts_conflict(self):
        store, _ = self.open_store()

        first_line = self.line(
            source_record_reference="record_shared",
            source_timestamp_us=1_000_000,
        )
        conflict_line = self.line(
            source_record_reference="record_shared",
            source_timestamp_us=1_000_001,
        )

        summary = self.replay(
            [first_line, conflict_line],
            store,
        )

        self.assertEqual(
            summary,
            ReplaySummaryV1(
                total_records=2,
                inserted=1,
                duplicate=0,
                identity_conflict=1,
            ),
        )

        first_event = self.decode([first_line])[0]
        stored = store.get_observation_event(
            first_event.observation_id
        )

        self.assertIsNotNone(stored)
        self.assertEqual(
            stored.source_timestamp_us,
            1_000_000,
        )

    def test_malformed_json_fails_before_any_write(self):
        store, path = self.open_store()

        with self.assertRaises(SyntheticJsonlDecodeError):
            self.replay(
                [
                    self.line(),
                    '{"source_record_reference":',
                ],
                store,
            )

        self.assertEqual(self.stored_event_count(path), 0)

    def test_blank_line_fails_before_any_write(self):
        store, path = self.open_store()

        with self.assertRaises(SyntheticJsonlDecodeError):
            self.replay(
                [
                    self.line(),
                    "   ",
                ],
                store,
            )

        self.assertEqual(self.stored_event_count(path), 0)

    def test_scalar_and_list_json_fail_before_any_write(self):
        store, path = self.open_store()

        for invalid_value in (
            "[]",
            "1",
            "null",
            '"text"',
        ):
            with self.subTest(value=invalid_value):
                with self.assertRaises(
                    SyntheticJsonlDecodeError
                ):
                    self.replay(
                        [
                            self.line(),
                            invalid_value,
                        ],
                        store,
                    )

                self.assertEqual(
                    self.stored_event_count(path),
                    0,
                )

    def test_unknown_field_fails_before_any_write(self):
        store, path = self.open_store()
        invalid = self.record()
        invalid["unexpected_field"] = "value"

        with self.assertRaises(SyntheticJsonlDecodeError):
            self.replay(
                [
                    self.line(),
                    json.dumps(invalid),
                ],
                store,
            )

        self.assertEqual(self.stored_event_count(path), 0)

    def test_missing_required_field_fails_before_any_write(self):
        store, path = self.open_store()
        invalid = {
            "source_timestamp_us": 1_000_000,
        }

        with self.assertRaises(SyntheticJsonlDecodeError):
            self.replay(
                [
                    self.line(),
                    json.dumps(invalid),
                ],
                store,
            )

        self.assertEqual(self.stored_event_count(path), 0)

    def test_invalid_optional_pairs_fail_before_any_write(self):
        store, path = self.open_store()

        invalid_cases = (
            {
                "device_identifier": "device_only",
            },
            {
                "device_identifier_kind": "synthetic_id",
            },
            {
                "signal_strength": -42,
            },
            {
                "signal_strength_unit": "synthetic_unit",
            },
        )

        for optional_values in invalid_cases:
            with self.subTest(values=optional_values):
                invalid_line = json.dumps(
                    self.record(**optional_values)
                )

                with self.assertRaises(
                    SyntheticJsonlDecodeError
                ):
                    self.replay(
                        [
                            self.line(),
                            invalid_line,
                        ],
                        store,
                    )

                self.assertEqual(
                    self.stored_event_count(path),
                    0,
                )

    def test_non_string_line_fails_before_any_write(self):
        store, path = self.open_store()

        with self.assertRaises(SyntheticJsonlDecodeError):
            self.replay(
                [
                    self.line(),
                    123,
                ],
                store,
            )

        self.assertEqual(self.stored_event_count(path), 0)

    def test_errors_do_not_expose_record_content_or_hmac_key(self):
        store, path = self.open_store()

        private_identifier = "private-record-content"
        private_field_name = "private-unknown-field-name"
        private_value = "private-field-value"
        private_key = b"private-hmac-key"

        invalid = {
            "source_record_reference": private_identifier,
            "source_timestamp_us": 1_000_000,
            private_field_name: private_value,
        }

        with self.assertRaises(
            SyntheticJsonlDecodeError
        ) as context:
            self.replay(
                [json.dumps(invalid)],
                store,
                hmac_key=private_key,
            )

        message = str(context.exception)

        self.assertNotIn(private_identifier, message)
        self.assertNotIn(private_field_name, message)
        self.assertNotIn(private_value, message)
        self.assertNotIn(
            private_key.decode("ascii"),
            message,
        )
        self.assertEqual(self.stored_event_count(path), 0)

    def test_summary_is_frozen_and_counts_only(self):
        summary = ReplaySummaryV1(
            total_records=3,
            inserted=1,
            duplicate=1,
            identity_conflict=1,
        )

        self.assertEqual(
            tuple(field.name for field in fields(summary)),
            (
                "total_records",
                "inserted",
                "duplicate",
                "identity_conflict",
            ),
        )

        with self.assertRaises(FrozenInstanceError):
            summary.inserted = 2

        with self.assertRaises(ValueError):
            ReplaySummaryV1(
                total_records=1,
                inserted=1,
                duplicate=1,
                identity_conflict=0,
            )

    def test_unexpected_store_result_fails_closed(self):
        store, path = self.open_store()

        with patch.object(
            store,
            "insert_observation_event",
            return_value="unexpected",
        ):
            with self.assertRaises(RuntimeError):
                self.replay(
                    [self.line()],
                    store,
                )

        self.assertEqual(self.stored_event_count(path), 0)


if __name__ == "__main__":
    unittest.main()
