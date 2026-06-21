from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from observation_location_link_writer import (
    LocationLinkWriteSummaryV1,
)
from observation_store import ObservationStore
from synthetic_jsonl_adapter import replay_synthetic_jsonl
from synthetic_operator_fix_jsonl_adapter import (
    SyntheticOperatorFixJsonlDecodeError,
    decode_synthetic_operator_fix_jsonl,
    replay_synthetic_operator_fix_jsonl,
)


class SyntheticOperatorFixJsonlAdapterTests(unittest.TestCase):
    KEY = b"synthetic-operator-fix-jsonl-test-key"

    @staticmethod
    def record(
        *,
        source_record_reference="fix_alpha",
        operator_fix_timestamp_us=1_000_100,
        operator_latitude=51.5,
        operator_longitude=7.4,
        **optional,
    ):
        value = {
            "source_record_reference": source_record_reference,
            "operator_fix_timestamp_us": operator_fix_timestamp_us,
            "operator_latitude": operator_latitude,
            "operator_longitude": operator_longitude,
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
        self.addCleanup(tempdir.cleanup)

        path = Path(tempdir.name) / "observations.sqlite"
        store = ObservationStore(path)
        self.addCleanup(store.close)

        return store

    def seed_event(
        self,
        store,
        *,
        timestamp_us=1_000_000,
        session_id="collection_alpha",
        reference="event_alpha",
    ):
        return replay_synthetic_jsonl(
            [
                json.dumps(
                    {
                        "source_record_reference": reference,
                        "source_timestamp_us": timestamp_us,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            ],
            store=store,
            hmac_key=self.KEY,
            collection_session_id=session_id,
            sensor_id="event_sensor",
            ingest_timestamp_us=2_000_000,
        )

    def decode(self, lines, **overrides):
        values = {
            "hmac_key": self.KEY,
            "collection_session_id": "collection_alpha",
            "sensor_id": "gps_sensor",
            "ingest_timestamp_us": 2_000_100,
        }
        values.update(overrides)

        return decode_synthetic_operator_fix_jsonl(
            lines,
            **values,
        )

    def replay(self, lines, store, **overrides):
        values = {
            "store": store,
            "hmac_key": self.KEY,
            "collection_session_id": "collection_alpha",
            "sensor_id": "gps_sensor",
            "ingest_timestamp_us": 2_000_100,
            "max_delta_us": 1_000,
        }
        values.update(overrides)

        return replay_synthetic_operator_fix_jsonl(
            lines,
            **values,
        )

    def test_decode_valid_single_multiple_and_optional_accuracy(self):
        single = self.decode(
            [
                self.line(
                    operator_location_accuracy_m=3.5,
                )
            ]
        )

        self.assertIsInstance(single, tuple)
        self.assertEqual(len(single), 1)
        self.assertEqual(
            single[0].operator_location_accuracy_m,
            3.5,
        )

        multiple = self.decode(
            [
                self.line(
                    source_record_reference="fix_first",
                    operator_fix_timestamp_us=1_000_100,
                ),
                self.line(
                    source_record_reference="fix_second",
                    operator_fix_timestamp_us=1_000_200,
                    operator_location_accuracy_m=None,
                ),
            ]
        )

        self.assertEqual(
            tuple(
                fix.source_record_reference
                for fix in multiple
            ),
            (
                "fix_first",
                "fix_second",
            ),
        )
        self.assertIsNone(
            multiple[1].operator_location_accuracy_m
        )

    def test_adapter_controls_source_provenance_and_zero_coordinates(self):
        fix = self.decode(
            [
                self.line(
                    operator_latitude=0,
                    operator_longitude=0,
                )
            ],
            collection_session_id="collection_beta",
            sensor_id="gps_beta",
            ingest_timestamp_us=9_000_000,
        )[0]

        self.assertEqual(
            fix.source_type,
            "synthetic.operator_fix_jsonl",
        )
        self.assertEqual(
            fix.collection_session_id,
            "collection_beta",
        )
        self.assertEqual(fix.sensor_id, "gps_beta")
        self.assertEqual(fix.ingest_timestamp_us, 9_000_000)
        self.assertEqual(fix.operator_latitude, 0)
        self.assertEqual(fix.operator_longitude, 0)
        self.assertEqual(
            fix.provenance.collector_name,
            "cyt.synthetic_operator_fix_jsonl_adapter",
        )
        self.assertEqual(
            fix.provenance.collector_version,
            "1.0",
        )
        self.assertEqual(
            fix.provenance.ingest_mode,
            "replay",
        )
        self.assertEqual(
            fix.provenance.source_schema_version,
            "cyt.synthetic-operator-fix-jsonl.v1",
        )

    def test_empty_input_returns_empty_tuple(self):
        self.assertEqual(self.decode([]), ())

    def test_end_to_end_replay_inserts_bounded_link(self):
        store = self.open_store()
        self.seed_event(store)

        summary = self.replay(
            [
                self.line(
                    operator_fix_timestamp_us=1_000_100,
                    operator_location_accuracy_m=4.0,
                )
            ],
            store,
            max_delta_us=100,
        )

        self.assertEqual(
            summary,
            LocationLinkWriteSummaryV1(
                total_candidates=1,
                inserted=1,
                duplicate=0,
                identity_conflict=0,
            ),
        )

        links = store.list_observation_location_links()

        self.assertEqual(len(links), 1)
        self.assertEqual(
            links[0].source_to_fix_delta_us,
            100,
        )
        self.assertEqual(
            links[0].correlation_method,
            "nearest_fix_bounded",
        )
        self.assertEqual(
            links[0].correlation_version,
            "1.0",
        )
        self.assertEqual(
            links[0].operator_location_accuracy_m,
            4.0,
        )

    def test_replay_counts_duplicate(self):
        store = self.open_store()
        self.seed_event(store)

        lines = [self.line()]

        first = self.replay(lines, store)
        second = self.replay(lines, store)

        self.assertEqual(first.inserted, 1)
        self.assertEqual(
            second,
            LocationLinkWriteSummaryV1(
                total_candidates=1,
                inserted=0,
                duplicate=1,
                identity_conflict=0,
            ),
        )

    def test_same_fix_identity_changed_coordinates_counts_conflict(self):
        store = self.open_store()
        self.seed_event(store)

        first = self.replay(
            [
                self.line(
                    source_record_reference="shared_fix",
                    operator_latitude=51.5,
                )
            ],
            store,
        )

        second = self.replay(
            [
                self.line(
                    source_record_reference="shared_fix",
                    operator_latitude=52.0,
                )
            ],
            store,
        )

        self.assertEqual(first.inserted, 1)
        self.assertEqual(
            second,
            LocationLinkWriteSummaryV1(
                total_candidates=1,
                inserted=0,
                duplicate=0,
                identity_conflict=1,
            ),
        )
        self.assertEqual(
            store.list_observation_location_links()[0]
            .operator_latitude,
            51.5,
        )

    def test_out_of_window_produces_zero_summary(self):
        store = self.open_store()
        self.seed_event(store)

        summary = self.replay(
            [
                self.line(
                    operator_fix_timestamp_us=1_000_101,
                )
            ],
            store,
            max_delta_us=100,
        )

        self.assertEqual(summary.total_candidates, 0)
        self.assertEqual(
            store.list_observation_location_links(),
            (),
        )

    def test_collection_session_isolation_produces_zero_summary(self):
        store = self.open_store()
        self.seed_event(
            store,
            session_id="collection_beta",
        )

        summary = self.replay(
            [self.line()],
            store,
            collection_session_id="collection_alpha",
        )

        self.assertEqual(summary.total_candidates, 0)
        self.assertEqual(
            store.list_observation_location_links(),
            (),
        )

    def test_blank_line_fails_before_write(self):
        store = self.open_store()
        self.seed_event(store)

        with self.assertRaises(
            SyntheticOperatorFixJsonlDecodeError
        ):
            self.replay(
                [
                    self.line(),
                    "   ",
                ],
                store,
            )

        self.assertEqual(
            store.list_observation_location_links(),
            (),
        )

    def test_invalid_input_shapes_fail_closed(self):
        for value in (
            self.line(),
            self.line().encode("utf-8"),
        ):
            with self.subTest(container_type=type(value)):
                with self.assertRaises(
                    SyntheticOperatorFixJsonlDecodeError
                ):
                    self.decode(value)

        store = self.open_store()
        self.seed_event(store)

        invalid_lines = (
            [123],
            ["[]"],
            ["1"],
            ["null"],
            ['"text"'],
        )

        for lines in invalid_lines:
            with self.subTest(lines=lines):
                with self.assertRaises(
                    SyntheticOperatorFixJsonlDecodeError
                ):
                    self.replay(lines, store)

                self.assertEqual(
                    store.list_observation_location_links(),
                    (),
                )

    def test_unknown_and_missing_fields_fail_before_write(self):
        store = self.open_store()
        self.seed_event(store)

        unknown = self.record()
        unknown["unexpected_field"] = "value"

        missing = self.record()
        del missing["operator_longitude"]

        for record in (unknown, missing):
            with self.subTest(keys=tuple(sorted(record))):
                with self.assertRaises(
                    SyntheticOperatorFixJsonlDecodeError
                ):
                    self.replay(
                        [json.dumps(record)],
                        store,
                    )

                self.assertEqual(
                    store.list_observation_location_links(),
                    (),
                )

    def test_invalid_record_fields_fail_before_write(self):
        store = self.open_store()
        self.seed_event(store)

        invalid_records = (
            self.record(operator_fix_timestamp_us=True),
            self.record(operator_fix_timestamp_us=-1),
            self.record(operator_latitude=91),
            self.record(operator_longitude=181),
            self.record(operator_location_accuracy_m=-1),
        )

        for record in invalid_records:
            with self.subTest(record=record):
                with self.assertRaises(
                    SyntheticOperatorFixJsonlDecodeError
                ):
                    self.replay(
                        [json.dumps(record)],
                        store,
                    )

                self.assertEqual(
                    store.list_observation_location_links(),
                    (),
                )

    def test_errors_do_not_expose_record_content_or_key(self):
        store = self.open_store()

        private_reference = "private-fix-reference"
        private_field = "private-field-name"
        private_value = "private-field-value"
        private_key = b"private-hmac-key"

        invalid = self.record(
            source_record_reference=private_reference,
        )
        invalid[private_field] = private_value

        with self.assertRaises(
            SyntheticOperatorFixJsonlDecodeError
        ) as context:
            self.replay(
                [json.dumps(invalid)],
                store,
                hmac_key=private_key,
            )

        message = str(context.exception)

        self.assertNotIn(private_reference, message)
        self.assertNotIn(private_field, message)
        self.assertNotIn(private_value, message)
        self.assertNotIn(
            private_key.decode("ascii"),
            message,
        )

    def test_invalid_max_delta_fails_before_write(self):
        store = self.open_store()
        self.seed_event(store)

        for value in (-1, True, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.replay(
                        [self.line()],
                        store,
                        max_delta_us=value,
                    )

                self.assertEqual(
                    store.list_observation_location_links(),
                    (),
                )

    def test_replay_delegates_decoded_fixes_to_orchestrator(self):
        store = self.open_store()

        lines = [
            self.line(
                source_record_reference="fix_first",
            ),
            self.line(
                source_record_reference="fix_second",
                operator_fix_timestamp_us=1_000_200,
            ),
        ]

        expected = LocationLinkWriteSummaryV1(
            total_candidates=2,
            inserted=1,
            duplicate=1,
            identity_conflict=0,
        )

        with patch(
            "synthetic_operator_fix_jsonl_adapter."
            "run_bounded_observation_location_link_correlation",
            return_value=expected,
        ) as orchestrator:
            result = self.replay(
                lines,
                store,
                max_delta_us=250,
            )

        self.assertIs(result, expected)

        orchestrator.assert_called_once_with(
            store=store,
            hmac_key=self.KEY,
            operator_fixes=self.decode(lines),
            max_delta_us=250,
            collection_session_id="collection_alpha",
        )

    def test_late_decode_error_prevents_earlier_valid_record_write(self):
        store = self.open_store()
        self.seed_event(store)

        with self.assertRaises(
            SyntheticOperatorFixJsonlDecodeError
        ):
            self.replay(
                [
                    self.line(),
                    '{"source_record_reference":',
                ],
                store,
            )

        self.assertEqual(
            store.list_observation_location_links(),
            (),
        )


if __name__ == "__main__":
    unittest.main()
