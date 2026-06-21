from __future__ import annotations

import unittest

from bounded_gps_correlator import (
    correlate_observations_to_operator_fixes,
)
from observation_contract import (
    ObservationProvenanceV1,
    create_observation_event,
    create_observation_location_link,
    create_operator_fix,
)


class BoundedGpsCorrelatorTests(unittest.TestCase):
    KEY = b"synthetic-bounded-correlator-key"

    @staticmethod
    def provenance():
        return ObservationProvenanceV1(
            collector_name="synthetic_correlator_fixture",
            collector_version="1.0",
            ingest_mode="replay",
            source_schema_version="synthetic-v1",
        )

    def event(
        self,
        *,
        timestamp_us=1_000_000,
        session_id="collection_alpha",
        reference="event_alpha",
    ):
        return create_observation_event(
            hmac_key=self.KEY,
            collection_session_id=session_id,
            source_type="synthetic.event",
            sensor_id="event_sensor",
            source_timestamp_us=timestamp_us,
            ingest_timestamp_us=timestamp_us + 10,
            source_record_reference=reference,
            provenance=self.provenance(),
        )

    def fix(
        self,
        *,
        timestamp_us=1_000_000,
        session_id="collection_alpha",
        reference="fix_alpha",
        latitude=10.25,
        longitude=-20.5,
        accuracy=4.5,
    ):
        return create_operator_fix(
            hmac_key=self.KEY,
            collection_session_id=session_id,
            source_type="synthetic.operator_fix",
            sensor_id="gps_sensor",
            operator_fix_timestamp_us=timestamp_us,
            ingest_timestamp_us=timestamp_us + 20,
            source_record_reference=reference,
            provenance=self.provenance(),
            operator_latitude=latitude,
            operator_longitude=longitude,
            operator_location_accuracy_m=accuracy,
        )

    def correlate(
        self,
        *,
        observations,
        fixes,
        max_delta_us=1_000,
        existing_links=(),
    ):
        return correlate_observations_to_operator_fixes(
            hmac_key=self.KEY,
            observations=tuple(observations),
            operator_fixes=tuple(fixes),
            max_delta_us=max_delta_us,
            existing_location_links=tuple(existing_links),
        )

    def test_exact_match_creates_zero_delta_link(self):
        event = self.event()
        fix = self.fix(
            latitude=11.5,
            longitude=-21.5,
            accuracy=3.25,
        )

        links = self.correlate(
            observations=(event,),
            fixes=(fix,),
        )

        self.assertEqual(len(links), 1)
        link = links[0]
        self.assertEqual(link.observation_id, event.observation_id)
        self.assertEqual(link.operator_fix_id, fix.operator_fix_id)
        self.assertEqual(link.operator_fix_timestamp_us, 1_000_000)
        self.assertEqual(link.source_to_fix_delta_us, 0)
        self.assertEqual(link.correlation_method, "nearest_fix_bounded")
        self.assertEqual(link.correlation_version, "1.0")
        self.assertEqual(link.operator_latitude, 11.5)
        self.assertEqual(link.operator_longitude, -21.5)
        self.assertEqual(link.operator_location_accuracy_m, 3.25)

    def test_nearest_earlier_fix_preserves_negative_delta(self):
        event = self.event(timestamp_us=1_000_000)
        earlier = self.fix(
            timestamp_us=999_900,
            reference="earlier",
        )
        later = self.fix(
            timestamp_us=1_000_500,
            reference="later",
        )

        link = self.correlate(
            observations=(event,),
            fixes=(later, earlier),
        )[0]

        self.assertEqual(link.operator_fix_id, earlier.operator_fix_id)
        self.assertEqual(link.source_to_fix_delta_us, -100)

    def test_nearest_later_fix_preserves_positive_delta(self):
        event = self.event(timestamp_us=1_000_000)
        earlier = self.fix(
            timestamp_us=999_000,
            reference="earlier",
        )
        later = self.fix(
            timestamp_us=1_000_100,
            reference="later",
        )

        link = self.correlate(
            observations=(event,),
            fixes=(earlier, later),
        )[0]

        self.assertEqual(link.operator_fix_id, later.operator_fix_id)
        self.assertEqual(link.source_to_fix_delta_us, 100)

    def test_equal_distance_prefers_earlier_fix(self):
        event = self.event(timestamp_us=1_000_000)
        earlier = self.fix(
            timestamp_us=999_900,
            reference="earlier",
        )
        later = self.fix(
            timestamp_us=1_000_100,
            reference="later",
        )

        link = self.correlate(
            observations=(event,),
            fixes=(later, earlier),
        )[0]

        self.assertEqual(link.operator_fix_id, earlier.operator_fix_id)
        self.assertEqual(link.source_to_fix_delta_us, -100)

    def test_equal_timestamp_uses_fix_id_as_final_tie_break(self):
        event = self.event()
        first = self.fix(reference="fix_first")
        second = self.fix(reference="fix_second")
        expected = min(
            (first, second),
            key=lambda fix: fix.operator_fix_id,
        )

        link = self.correlate(
            observations=(event,),
            fixes=(second, first),
        )[0]

        self.assertEqual(link.operator_fix_id, expected.operator_fix_id)

    def test_window_boundary_is_inclusive(self):
        event = self.event(timestamp_us=1_000_000)
        fix = self.fix(timestamp_us=1_000_250)

        link = self.correlate(
            observations=(event,),
            fixes=(fix,),
            max_delta_us=250,
        )[0]

        self.assertEqual(link.source_to_fix_delta_us, 250)

    def test_out_of_window_remains_unknown(self):
        event = self.event(timestamp_us=1_000_000)
        fix = self.fix(timestamp_us=1_000_251)

        links = self.correlate(
            observations=(event,),
            fixes=(fix,),
            max_delta_us=250,
        )

        self.assertEqual(links, ())

    def test_missing_fixes_remain_unknown(self):
        links = self.correlate(
            observations=(self.event(),),
            fixes=(),
        )

        self.assertEqual(links, ())

    def test_different_collection_session_does_not_match(self):
        event = self.event(session_id="collection_alpha")
        fix = self.fix(session_id="collection_beta")

        links = self.correlate(
            observations=(event,),
            fixes=(fix,),
        )

        self.assertEqual(links, ())

    def test_missing_accuracy_is_preserved(self):
        event = self.event()
        fix = self.fix(accuracy=None)

        link = self.correlate(
            observations=(event,),
            fixes=(fix,),
        )[0]

        self.assertIsNone(link.operator_location_accuracy_m)

    def test_same_source_record_link_is_not_overwritten(self):
        event = self.event()
        fix = self.fix()
        same_source_link = create_observation_location_link(
            hmac_key=self.KEY,
            observation=event,
            operator_fix_id=(
                event.observation_id + ".same_packet_fix_v1"
            ),
            operator_latitude=12.0,
            operator_longitude=-22.0,
            operator_fix_timestamp_us=event.source_timestamp_us,
            correlation_method="same_source_record",
            correlation_version="1.0",
        )

        links = self.correlate(
            observations=(event,),
            fixes=(fix,),
            existing_links=(same_source_link,),
        )

        self.assertEqual(links, ())

    def test_same_source_record_only_suppresses_its_parent(self):
        first_event = self.event(
            timestamp_us=1_000_000,
            reference="event_first",
        )
        second_event = self.event(
            timestamp_us=1_000_100,
            reference="event_second",
        )
        fix = self.fix(timestamp_us=1_000_050)
        same_source_link = create_observation_location_link(
            hmac_key=self.KEY,
            observation=first_event,
            operator_fix_id=(
                first_event.observation_id + ".same_packet_fix_v1"
            ),
            operator_latitude=12.0,
            operator_longitude=-22.0,
            operator_fix_timestamp_us=first_event.source_timestamp_us,
            correlation_method="same_source_record",
            correlation_version="1.0",
        )

        links = self.correlate(
            observations=(second_event, first_event),
            fixes=(fix,),
            existing_links=(same_source_link,),
        )

        self.assertEqual(len(links), 1)
        self.assertEqual(
            links[0].observation_id,
            second_event.observation_id,
        )

    def test_other_existing_method_does_not_claim_same_packet(self):
        event = self.event()
        old_fix = self.fix(reference="old_fix")
        new_fix = self.fix(reference="new_fix")
        existing = create_observation_location_link(
            hmac_key=self.KEY,
            observation=event,
            operator_fix_id=old_fix.operator_fix_id,
            operator_latitude=old_fix.operator_latitude,
            operator_longitude=old_fix.operator_longitude,
            operator_fix_timestamp_us=old_fix.operator_fix_timestamp_us,
            correlation_method="legacy_nearest",
            correlation_version="1.0",
        )

        links = self.correlate(
            observations=(event,),
            fixes=(new_fix,),
            existing_links=(existing,),
        )

        self.assertEqual(len(links), 1)
        self.assertEqual(
            links[0].operator_fix_id,
            new_fix.operator_fix_id,
        )

    def test_input_order_does_not_change_result(self):
        first_event = self.event(
            timestamp_us=1_000_200,
            reference="event_later",
        )
        second_event = self.event(
            timestamp_us=1_000_000,
            reference="event_earlier",
        )
        first_fix = self.fix(
            timestamp_us=1_000_210,
            reference="fix_later",
        )
        second_fix = self.fix(
            timestamp_us=999_990,
            reference="fix_earlier",
        )

        forward = self.correlate(
            observations=(first_event, second_event),
            fixes=(first_fix, second_fix),
        )
        reversed_inputs = self.correlate(
            observations=(second_event, first_event),
            fixes=(second_fix, first_fix),
        )

        self.assertEqual(forward, reversed_inputs)

    def test_output_is_ordered_by_source_time_then_observation_id(self):
        same_time_a = self.event(
            timestamp_us=1_000_000,
            reference="same_time_a",
        )
        same_time_b = self.event(
            timestamp_us=1_000_000,
            reference="same_time_b",
        )
        later = self.event(
            timestamp_us=1_000_100,
            reference="later",
        )
        fix = self.fix(timestamp_us=1_000_000)

        links = self.correlate(
            observations=(later, same_time_b, same_time_a),
            fixes=(fix,),
        )

        expected_observation_ids = tuple(
            event.observation_id
            for event in sorted(
                (same_time_a, same_time_b, later),
                key=lambda event: (
                    event.source_timestamp_us,
                    event.observation_id,
                ),
            )
        )

        self.assertEqual(
            tuple(link.observation_id for link in links),
            expected_observation_ids,
        )

    def test_invalid_max_delta_is_rejected(self):
        event = self.event()
        fix = self.fix()

        for value in (-1, True, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.correlate(
                        observations=(event,),
                        fixes=(fix,),
                        max_delta_us=value,
                    )


if __name__ == "__main__":
    unittest.main()
