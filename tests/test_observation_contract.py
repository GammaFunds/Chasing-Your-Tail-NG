from dataclasses import FrozenInstanceError
import math
import unittest

from observation_contract import (
    ObservationEventV1,
    ObservationLocationLinkV1,
    ObservationProvenanceV1,
    OperatorFixV1,
    compare_observation_source_facts,
    compare_operator_fix_source_facts,
    create_observation_event,
    create_observation_location_link,
    create_operator_fix,
)


class ObservationContractV1Tests(unittest.TestCase):
    KEY = b"synthetic-contract-test-key"

    @staticmethod
    def provenance(
        *,
        collector_name="synthetic_collector",
        collector_version="1.2.3",
        ingest_mode="live",
        source_schema_version="synthetic-v1",
    ):
        return ObservationProvenanceV1(
            collector_name=collector_name,
            collector_version=collector_version,
            ingest_mode=ingest_mode,
            source_schema_version=source_schema_version,
        )

    def event(self, **overrides):
        values = {
            "hmac_key": self.KEY,
            "collection_session_id": "collection_alpha",
            "source_type": "synthetic.event",
            "sensor_id": "sensor_alpha",
            "source_timestamp_us": 1_000_000,
            "ingest_timestamp_us": 1_000_250,
            "source_record_reference": "record_alpha",
            "provenance": self.provenance(),
            "device_identifier": None,
            "device_identifier_kind": None,
            "signal_strength": None,
            "signal_strength_unit": None,
        }
        values.update(overrides)
        return create_observation_event(**values)

    def location_link(self, observation=None, **overrides):
        values = {
            "hmac_key": self.KEY,
            "observation": observation or self.event(),
            "operator_fix_id": "fix_alpha",
            "operator_latitude": 10.25,
            "operator_longitude": -20.5,
            "operator_fix_timestamp_us": 1_000_750,
            "correlation_method": "nearest_fix_bounded",
            "correlation_version": "1.0",
            "operator_location_accuracy_m": 4.5,
        }
        values.update(overrides)
        return create_observation_location_link(**values)

    def test_identical_identity_inputs_are_deterministic(self):
        first = self.event()
        second = self.event()

        self.assertEqual(first.observation_id, second.observation_id)
        self.assertRegex(
            first.observation_id,
            r"^obs_v1_[0-9a-f]{64}$",
        )

    def test_every_identity_input_changes_observation_id(self):
        baseline = self.event()

        cases = {
            "source_type": {
                "source_type": "synthetic.alternate",
            },
            "sensor_id": {
                "sensor_id": "sensor_beta",
            },
            "collection_session_id": {
                "collection_session_id": "collection_beta",
            },
            "source_record_reference": {
                "source_record_reference": "record_beta",
            },
        }

        for name, overrides in cases.items():
            with self.subTest(name=name):
                changed = self.event(**overrides)
                self.assertNotEqual(
                    baseline.observation_id,
                    changed.observation_id,
                )

    def test_nonidentity_fields_do_not_change_observation_id(self):
        baseline = self.event()

        cases = {
            "source_timestamp": {
                "source_timestamp_us": 2_000_000,
            },
            "ingest_timestamp": {
                "ingest_timestamp_us": 2_000_250,
            },
            "device": {
                "device_identifier": "device_alpha",
                "device_identifier_kind": "synthetic_id",
            },
            "signal": {
                "signal_strength": -42.5,
                "signal_strength_unit": "synthetic_unit",
            },
            "provenance": {
                "provenance": self.provenance(
                    collector_name="other_collector",
                    ingest_mode="replay",
                ),
            },
        }

        for name, overrides in cases.items():
            with self.subTest(name=name):
                changed = self.event(**overrides)
                self.assertEqual(
                    baseline.observation_id,
                    changed.observation_id,
                )

    def test_different_hmac_key_changes_local_identity(self):
        baseline = self.event()
        changed = self.event(
            hmac_key=b"other-synthetic-contract-test-key"
        )

        self.assertNotEqual(
            baseline.observation_id,
            changed.observation_id,
        )

    def test_valid_event_fields_and_immutability(self):
        event = self.event(
            device_identifier="device_alpha",
            device_identifier_kind="synthetic_id",
            signal_strength=-37,
            signal_strength_unit="synthetic_unit",
        )

        self.assertIsInstance(event, ObservationEventV1)
        self.assertEqual(event.schema_version, "1.0")
        self.assertEqual(event.record_kind, "observation_event")
        self.assertEqual(event.source_timestamp_us, 1_000_000)

        with self.assertRaises(FrozenInstanceError):
            event.sensor_id = "sensor_changed"

    def test_invalid_timestamp_types_and_values_are_rejected(self):
        for field in (
            "source_timestamp_us",
            "ingest_timestamp_us",
        ):
            for value in (True, 1.25, -1):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        self.event(**{field: value})

    def test_source_timestamp_is_mandatory(self):
        values = {
            "hmac_key": self.KEY,
            "collection_session_id": "collection_alpha",
            "source_type": "synthetic.event",
            "sensor_id": "sensor_alpha",
            "ingest_timestamp_us": 1_000_250,
            "source_record_reference": "record_alpha",
            "provenance": self.provenance(),
        }

        with self.assertRaises(TypeError):
            create_observation_event(**values)

    def test_invalid_source_types_are_rejected(self):
        invalid_values = (
            "Synthetic.event",
            "synthetic",
            "synthetic event",
            ".event",
            "synthetic.",
            "synthetic..event",
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.event(source_type=value)

    def test_device_identifier_pair_is_enforced(self):
        cases = (
            {
                "device_identifier": "device_alpha",
                "device_identifier_kind": None,
            },
            {
                "device_identifier": None,
                "device_identifier_kind": "synthetic_id",
            },
        )

        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.event(**values)

    def test_signal_pair_and_finite_value_are_enforced(self):
        invalid_cases = (
            {
                "signal_strength": -10,
                "signal_strength_unit": None,
            },
            {
                "signal_strength": None,
                "signal_strength_unit": "synthetic_unit",
            },
            {
                "signal_strength": math.nan,
                "signal_strength_unit": "synthetic_unit",
            },
            {
                "signal_strength": math.inf,
                "signal_strength_unit": "synthetic_unit",
            },
            {
                "signal_strength": True,
                "signal_strength_unit": "synthetic_unit",
            },
        )

        for values in invalid_cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.event(**values)

    def test_provenance_modes_and_fields_are_validated(self):
        for ingest_mode in ("live", "replay", "import"):
            with self.subTest(ingest_mode=ingest_mode):
                provenance = self.provenance(
                    ingest_mode=ingest_mode
                )
                self.assertEqual(
                    provenance.ingest_mode,
                    ingest_mode,
                )

        with self.assertRaises(ValueError):
            self.provenance(ingest_mode="other")

        with self.assertRaises(ValueError):
            self.provenance(collector_name="")

    def test_location_link_is_deterministic_and_signed(self):
        event = self.event()
        first = self.location_link(observation=event)
        second = self.location_link(observation=event)

        self.assertIsInstance(
            first,
            ObservationLocationLinkV1,
        )
        self.assertEqual(
            first.location_link_id,
            second.location_link_id,
        )
        self.assertRegex(
            first.location_link_id,
            r"^loc_v1_[0-9a-f]{64}$",
        )
        self.assertEqual(first.source_to_fix_delta_us, 750)
        self.assertEqual(
            first.record_kind,
            "observation_location_link",
        )

    def test_location_link_preserves_negative_delta(self):
        event = self.event(source_timestamp_us=2_000_000)
        link = self.location_link(
            observation=event,
            operator_fix_timestamp_us=1_999_500,
        )

        self.assertEqual(link.source_to_fix_delta_us, -500)

    def test_location_link_identity_inputs_change_link_id(self):
        baseline = self.location_link()

        cases = {
            "observation": {
                "observation": self.event(
                    collection_session_id="collection_beta"
                ),
            },
            "operator_fix_id": {
                "operator_fix_id": "fix_beta",
            },
            "correlation_method": {
                "correlation_method": "alternate_method",
            },
            "correlation_version": {
                "correlation_version": "1.1",
            },
        }

        for name, overrides in cases.items():
            with self.subTest(name=name):
                changed = self.location_link(**overrides)
                self.assertNotEqual(
                    baseline.location_link_id,
                    changed.location_link_id,
                )

    def test_invalid_location_values_are_rejected(self):
        invalid_cases = (
            {"operator_latitude": 90.0001},
            {"operator_latitude": -90.0001},
            {"operator_longitude": 180.0001},
            {"operator_longitude": -180.0001},
            {"operator_latitude": math.nan},
            {"operator_longitude": math.inf},
            {"operator_latitude": True},
            {"operator_location_accuracy_m": -0.1},
            {"operator_location_accuracy_m": math.inf},
            {"operator_fix_timestamp_us": True},
            {"operator_fix_timestamp_us": 1.5},
            {"operator_fix_timestamp_us": -1},
        )

        for values in invalid_cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.location_link(**values)

    def test_location_link_is_frozen(self):
        link = self.location_link()

        with self.assertRaises(FrozenInstanceError):
            link.operator_fix_id = "fix_changed"

    def test_duplicate_ignores_ingest_and_provenance(self):
        existing = self.event(
            device_identifier="device_alpha",
            device_identifier_kind="synthetic_id",
            signal_strength=-42,
            signal_strength_unit="synthetic_unit",
        )
        incoming = self.event(
            ingest_timestamp_us=9_000_000,
            provenance=self.provenance(
                collector_version="9.9.9",
                ingest_mode="replay",
            ),
            device_identifier="device_alpha",
            device_identifier_kind="synthetic_id",
            signal_strength=-42,
            signal_strength_unit="synthetic_unit",
        )

        self.assertEqual(
            existing.observation_id,
            incoming.observation_id,
        )
        self.assertEqual(
            compare_observation_source_facts(
                existing,
                incoming,
            ),
            "duplicate",
        )

    def test_changed_source_facts_produce_identity_conflict(self):
        existing = self.event(
            device_identifier="device_alpha",
            device_identifier_kind="synthetic_id",
            signal_strength=-42,
            signal_strength_unit="synthetic_unit",
        )

        cases = {
            "source_type": {
                "source_type": "synthetic.alternate",
            },
            "sensor_id": {
                "sensor_id": "sensor_beta",
            },
            "collection_session_id": {
                "collection_session_id": "collection_beta",
            },
            "source_record_reference": {
                "source_record_reference": "record_beta",
            },
            "device_identifier": {
                "device_identifier": "device_beta",
                "device_identifier_kind": "synthetic_id",
            },
            "device_identifier_kind": {
                "device_identifier": "device_alpha",
                "device_identifier_kind": "alternate_id",
            },
            "source_timestamp": {
                "source_timestamp_us": 1_000_001,
            },
            "signal_strength": {
                "signal_strength": -43,
                "signal_strength_unit": "synthetic_unit",
            },
            "signal_strength_unit": {
                "signal_strength": -42,
                "signal_strength_unit": "alternate_unit",
            },
        }

        for name, overrides in cases.items():
            with self.subTest(name=name):
                incoming_values = {
                    "device_identifier": "device_alpha",
                    "device_identifier_kind": "synthetic_id",
                    "signal_strength": -42,
                    "signal_strength_unit": "synthetic_unit",
                }
                incoming_values.update(overrides)
                incoming = self.event(**incoming_values)

                self.assertEqual(
                    compare_observation_source_facts(
                        existing,
                        incoming,
                    ),
                    "identity_conflict",
                )

    def test_invalid_hmac_keys_are_rejected(self):
        for value in (b"", "not-bytes", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.event(hmac_key=value)


class OperatorFixV1Tests(unittest.TestCase):
    KEY = b"synthetic-contract-test-key"

    @staticmethod
    def provenance(
        *,
        collector_name="synthetic_collector",
        collector_version="1.2.3",
        ingest_mode="live",
        source_schema_version="synthetic-v1",
    ):
        return ObservationProvenanceV1(
            collector_name=collector_name,
            collector_version=collector_version,
            ingest_mode=ingest_mode,
            source_schema_version=source_schema_version,
        )

    def fix(self, **overrides):
        values = {
            "hmac_key": self.KEY,
            "collection_session_id": "collection_alpha",
            "source_type": "synthetic.gps",
            "sensor_id": "sensor_alpha",
            "operator_fix_timestamp_us": 1_000_000,
            "ingest_timestamp_us": 1_000_250,
            "source_record_reference": "fix_record_alpha",
            "provenance": self.provenance(),
            "operator_latitude": 33.0,
            "operator_longitude": -112.0,
            "operator_location_accuracy_m": 5.0,
        }
        values.update(overrides)
        return create_operator_fix(**values)

    def test_deterministic_identity_and_fix_v1_prefix(self):
        first = self.fix()
        second = self.fix()

        self.assertEqual(
            first.operator_fix_id,
            second.operator_fix_id,
        )
        self.assertRegex(
            first.operator_fix_id,
            r"^fix_v1_[0-9a-f]{64}$",
        )

    def test_every_identity_input_changes_operator_fix_id(self):
        baseline = self.fix()

        cases = {
            "source_type": {
                "source_type": "synthetic.alternate",
            },
            "sensor_id": {
                "sensor_id": "sensor_beta",
            },
            "collection_session_id": {
                "collection_session_id": "collection_beta",
            },
            "source_record_reference": {
                "source_record_reference": "fix_record_beta",
            },
        }

        for name, overrides in cases.items():
            with self.subTest(name=name):
                changed = self.fix(**overrides)
                self.assertNotEqual(
                    baseline.operator_fix_id,
                    changed.operator_fix_id,
                )

    def test_nonidentity_fields_do_not_change_operator_fix_id(
        self,
    ):
        baseline = self.fix()

        cases = {
            "operator_fix_timestamp_us": {
                "operator_fix_timestamp_us": 2_000_000,
            },
            "ingest_timestamp_us": {
                "ingest_timestamp_us": 2_000_250,
            },
            "operator_latitude": {
                "operator_latitude": 40.0,
            },
            "operator_longitude": {
                "operator_longitude": -75.0,
            },
            "operator_location_accuracy_m": {
                "operator_location_accuracy_m": 10.0,
            },
            "provenance": {
                "provenance": self.provenance(
                    collector_name="other_collector",
                    ingest_mode="replay",
                ),
            },
        }

        for name, overrides in cases.items():
            with self.subTest(name=name):
                changed = self.fix(**overrides)
                self.assertEqual(
                    baseline.operator_fix_id,
                    changed.operator_fix_id,
                )

    def test_changed_source_facts_produce_identity_conflict(
        self,
    ):
        existing = self.fix()

        cases = {
            "source_type": {
                "source_type": "synthetic.alternate",
            },
            "sensor_id": {
                "sensor_id": "sensor_beta",
            },
            "collection_session_id": {
                "collection_session_id": "collection_beta",
            },
            "source_record_reference": {
                "source_record_reference": "fix_record_beta",
            },
            "operator_fix_timestamp_us": {
                "operator_fix_timestamp_us": 2_000_000,
            },
            "operator_latitude": {
                "operator_latitude": 40.0,
            },
            "operator_longitude": {
                "operator_longitude": -75.0,
            },
            "operator_location_accuracy_m": {
                "operator_location_accuracy_m": 10.0,
            },
        }

        for name, overrides in cases.items():
            with self.subTest(name=name):
                incoming = self.fix(**overrides)
                self.assertEqual(
                    compare_operator_fix_source_facts(
                        existing,
                        incoming,
                    ),
                    "identity_conflict",
                )

    def test_changed_ingest_or_provenance_remains_duplicate(
        self,
    ):
        existing = self.fix()
        incoming = self.fix(
            ingest_timestamp_us=9_000_000,
            provenance=self.provenance(
                collector_version="9.9.9",
                ingest_mode="replay",
            ),
        )

        self.assertEqual(
            compare_operator_fix_source_facts(
                existing,
                incoming,
            ),
            "duplicate",
        )

    def test_legal_coordinates(self):
        coords = (
            (33.0, -112.0),
            (-33.0, 120.0),
            (90.0, 180.0),
            (-90.0, -180.0),
            (0.0, 0.0),
        )

        for lat, lon in coords:
            with self.subTest(lat=lat, lon=lon):
                fix = self.fix(
                    operator_latitude=lat,
                    operator_longitude=lon,
                )
                self.assertEqual(fix.operator_latitude, lat)
                self.assertEqual(fix.operator_longitude, lon)

    def test_rejects_malformed_operator_fix_id(self):
        with self.assertRaises(ValueError):
            OperatorFixV1(
                schema_version="1.0",
                record_kind="operator_fix",
                operator_fix_id="bad_id",
                collection_session_id="session_alpha",
                source_type="synthetic.gps",
                sensor_id="sensor_alpha",
                operator_fix_timestamp_us=1_000_000,
                ingest_timestamp_us=1_000_250,
                source_record_reference="record_alpha",
                provenance=ObservationProvenanceV1(
                    collector_name="test",
                    collector_version="1.0",
                    ingest_mode="live",
                ),
                operator_latitude=33.0,
                operator_longitude=-112.0,
            )

    def test_rejects_wrong_record_kind(self):
        with self.assertRaises(ValueError):
            OperatorFixV1(
                schema_version="1.0",
                record_kind="observation_event",
                operator_fix_id="fix_v1_"
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                collection_session_id="session_alpha",
                source_type="synthetic.gps",
                sensor_id="sensor_alpha",
                operator_fix_timestamp_us=1_000_000,
                ingest_timestamp_us=1_000_250,
                source_record_reference="record_alpha",
                provenance=ObservationProvenanceV1(
                    collector_name="test",
                    collector_version="1.0",
                    ingest_mode="live",
                ),
                operator_latitude=33.0,
                operator_longitude=-112.0,
            )

    def test_rejects_invalid_timestamps(self):
        for field in (
            "operator_fix_timestamp_us",
            "ingest_timestamp_us",
        ):
            for value in (True, 1.25, -1):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        self.fix(**{field: value})

    def test_rejects_nonfinite_or_out_of_range_coordinates(
        self,
    ):
        invalid_cases = (
            {"operator_latitude": 90.0001},
            {"operator_latitude": -90.0001},
            {"operator_longitude": 180.0001},
            {"operator_longitude": -180.0001},
            {"operator_latitude": math.nan},
            {"operator_longitude": math.inf},
            {"operator_latitude": True},
        )

        for values in invalid_cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.fix(**values)

    def test_rejects_invalid_accuracy(self):
        invalid_cases = (
            {"operator_location_accuracy_m": -0.1},
            {"operator_location_accuracy_m": math.inf},
            {"operator_location_accuracy_m": math.nan},
        )

        for values in invalid_cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.fix(**values)

    def test_optional_accuracy_allows_none(self):
        fix = self.fix(operator_location_accuracy_m=None)
        self.assertIsNone(fix.operator_location_accuracy_m)

    def test_operator_fix_is_frozen(self):
        fix = self.fix()

        with self.assertRaises(FrozenInstanceError):
            fix.sensor_id = "sensor_changed"


if __name__ == "__main__":
    unittest.main()
