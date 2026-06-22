from dataclasses import FrozenInstanceError
import unittest

from ground_truth_scenario_contract import (
    GroundTruthExpectedSummaryV1,
    GroundTruthScenarioManifestV1,
    REJECTION_STAGES,
    RECORD_KIND,
    SCHEMA_VERSION_V1,
)
from observation_location_link_writer import LocationLinkWriteSummaryV1
from synthetic_jsonl_adapter import ReplaySummaryV1


def _replay_summary(**kw):
    vals = {
        "total_records": 5,
        "inserted": 3,
        "duplicate": 2,
        "identity_conflict": 0,
    }
    vals.update(kw)
    return ReplaySummaryV1(**vals)


def _link_summary(**kw):
    vals = {
        "total_candidates": 2,
        "inserted": 2,
        "duplicate": 0,
        "identity_conflict": 0,
    }
    vals.update(kw)
    return LocationLinkWriteSummaryV1(**vals)


def _expected_summary(**kw):
    vals = {
        "outcome": "completed",
        "rejection_stage": None,
        "replay_summary": _replay_summary(),
        "location_link_write_summary": _link_summary(),
        "observation_event_count": 10,
        "observation_location_link_count": 2,
        "collection_session_count": 1,
        "source_membership_count": 1,
        "membership_close_count": 1,
        "session_close_count": 1,
        "route_count": 2,
        "analysis_session_count": 1,
        "unlinked_observation_count": 2,
        "route_point_counts": (3, 5),
        "route_source_time_bounds_us": (
            (1000, 4000),
            (2000, 7000),
        ),
        "source_to_fix_deltas_us": (50, 100),
    }
    vals.update(kw)
    return GroundTruthExpectedSummaryV1(**vals)


def _manifest(**kw):
    vals = {
        "schema_version": SCHEMA_VERSION_V1,
        "record_kind": RECORD_KIND,
        "scenario_id": "cyt.synthetic.basic_replay",
        "scenario_version": "1.0",
        "scenario_label": "Basic Replay Test",
        "tags": ("replay", "smoke"),
        "input_manifest_digest": "a" * 64,
        "expected_summary": _expected_summary(),
    }
    vals.update(kw)
    return GroundTruthScenarioManifestV1(**vals)


class GroundTruthExpectedSummaryV1Tests(unittest.TestCase):
    def test_valid_completed(self):
        s = _expected_summary()
        self.assertIsInstance(s, GroundTruthExpectedSummaryV1)
        self.assertEqual(s.outcome, "completed")
        self.assertIsNone(s.rejection_stage)
        self.assertEqual(s.observation_event_count, 10)
        self.assertEqual(s.observation_location_link_count, 2)
        self.assertEqual(s.collection_session_count, 1)
        self.assertEqual(s.source_membership_count, 1)
        self.assertEqual(s.membership_close_count, 1)
        self.assertEqual(s.session_close_count, 1)
        self.assertEqual(s.route_count, 2)
        self.assertEqual(s.analysis_session_count, 1)
        self.assertEqual(s.unlinked_observation_count, 2)
        self.assertEqual(s.route_point_counts, (3, 5))
        self.assertEqual(
            s.route_source_time_bounds_us,
            ((1000, 4000), (2000, 7000)),
        )
        self.assertEqual(s.source_to_fix_deltas_us, (50, 100))

    def test_valid_rejected_each_stage(self):
        for stage in sorted(REJECTION_STAGES):
            with self.subTest(stage=stage):
                s = _expected_summary(
                    outcome="rejected",
                    rejection_stage=stage,
                )
                self.assertEqual(s.outcome, "rejected")
                self.assertEqual(s.rejection_stage, stage)

    def test_completed_with_rejection_stage_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(
                outcome="completed",
                rejection_stage="observation_decode",
            )

    def test_rejected_without_stage_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(
                outcome="rejected",
                rejection_stage=None,
            )

    def test_invalid_outcome_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(outcome="unknown")

    def test_rejected_unrecognized_stage_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(
                outcome="rejected",
                rejection_stage="nonexistent_stage",
            )

    def test_rejects_bool_counts(self):
        for count_name in (
            "observation_event_count",
            "observation_location_link_count",
            "collection_session_count",
            "source_membership_count",
            "membership_close_count",
            "session_close_count",
            "route_count",
            "analysis_session_count",
            "unlinked_observation_count",
        ):
            with self.subTest(count_name=count_name):
                with self.assertRaises(ValueError):
                    _expected_summary(**{count_name: True})

    def test_rejects_negative_counts(self):
        for count_name in (
            "observation_event_count",
            "observation_location_link_count",
            "collection_session_count",
            "source_membership_count",
            "membership_close_count",
            "session_close_count",
            "route_count",
            "analysis_session_count",
            "unlinked_observation_count",
        ):
            with self.subTest(count_name=count_name):
                with self.assertRaises(ValueError):
                    _expected_summary(**{count_name: -1})

    def test_unlinked_exceeds_observations_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(
                observation_event_count=5,
                unlinked_observation_count=10,
            )

    def test_unlinked_equals_observations_allowed(self):
        s = _expected_summary(
            observation_event_count=10,
            unlinked_observation_count=10,
        )
        self.assertEqual(s.unlinked_observation_count, 10)

    def test_route_point_counts_must_be_tuple(self):
        with self.assertRaises(ValueError):
            _expected_summary(route_point_counts=[3, 5])

    def test_route_source_time_bounds_must_be_tuple(self):
        with self.assertRaises(ValueError):
            _expected_summary(
                route_source_time_bounds_us=[(1000, 4000)],
            )

    def test_route_source_time_bounds_element_must_be_2_tuple(self):
        with self.assertRaises(ValueError):
            _expected_summary(
                route_source_time_bounds_us=((1000, 4000, 5000),),
            )

    def test_route_bound_start_negative_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(
                route_source_time_bounds_us=((-1, 1000),),
            )

    def test_route_bound_end_negative_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(
                route_source_time_bounds_us=((1000, -1),),
            )

    def test_route_bound_start_after_end_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(
                route_source_time_bounds_us=((5000, 1000),),
            )

    def test_route_bound_start_bool_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(
                route_source_time_bounds_us=((True, 1000),),
            )

    def test_route_bound_end_bool_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(
                route_source_time_bounds_us=((1000, True),),
            )

    def test_route_bound_zero_start_allowed(self):
        s = _expected_summary(
            route_count=1,
            route_point_counts=(5,),
            route_source_time_bounds_us=((0, 1000),),
        )
        self.assertEqual(s.route_source_time_bounds_us[0][0], 0)

    def test_route_bound_start_equals_end_allowed(self):
        s = _expected_summary(
            route_count=1,
            route_point_counts=(5,),
            route_source_time_bounds_us=((1000, 1000),),
        )
        self.assertEqual(
            s.route_source_time_bounds_us[0][0],
            s.route_source_time_bounds_us[0][1],
        )

    def test_route_point_count_zero_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(route_point_counts=(0,))

    def test_route_point_count_bool_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(route_point_counts=(True,))

    def test_route_count_mismatch_point_counts_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(
                route_count=3,
                route_point_counts=(3, 5),
                route_source_time_bounds_us=((1000, 4000), (2000, 7000)),
            )

    def test_route_count_mismatch_bounds_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(
                route_count=3,
                route_point_counts=(3, 5, 7),
                route_source_time_bounds_us=((1000, 4000), (2000, 7000)),
            )

    def test_source_to_fix_deltas_must_be_tuple(self):
        with self.assertRaises(ValueError):
            _expected_summary(source_to_fix_deltas_us=[50, 100])

    def test_source_to_fix_delta_bool_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(source_to_fix_deltas_us=(True,))

    def test_negative_delta_allowed(self):
        s = _expected_summary(
            observation_location_link_count=3,
            source_to_fix_deltas_us=(-100, 0, 50),
        )
        self.assertEqual(s.source_to_fix_deltas_us, (-100, 0, 50))

    def test_delta_count_matches_observation_location_link_count(self):
        s = _expected_summary(
            observation_location_link_count=3,
            source_to_fix_deltas_us=(1, 2, 3),
        )
        self.assertEqual(len(s.source_to_fix_deltas_us), 3)

    def test_delta_count_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            _expected_summary(
                observation_location_link_count=2,
                source_to_fix_deltas_us=(1, 2, 3),
            )

    def test_replay_summary_type_check(self):
        with self.assertRaises(ValueError):
            _expected_summary(replay_summary="not-a-summary")

    def test_link_summary_type_check(self):
        with self.assertRaises(ValueError):
            _expected_summary(
                location_link_write_summary="not-a-summary",
            )

    def test_reuses_existing_replay_summary_counts(self):
        rs = ReplaySummaryV1(
            total_records=10, inserted=7, duplicate=2, identity_conflict=1,
        )
        s = _expected_summary(replay_summary=rs)
        self.assertIs(s.replay_summary, rs)
        self.assertEqual(s.replay_summary.inserted, 7)

    def test_reuses_existing_link_summary_counts(self):
        ls = LocationLinkWriteSummaryV1(
            total_candidates=3, inserted=1, duplicate=1, identity_conflict=1,
        )
        s = _expected_summary(location_link_write_summary=ls)
        self.assertIs(s.location_link_write_summary, ls)

    def test_removed_total_observations_stored_field(self):
        s = _expected_summary()
        self.assertFalse(hasattr(s, "total_observations_stored"))

    def test_removed_total_observations_loaded_field(self):
        s = _expected_summary()
        self.assertFalse(hasattr(s, "total_observations_loaded"))

    def test_removed_route_source_timestamp_starts_field(self):
        s = _expected_summary()
        self.assertFalse(hasattr(s, "route_source_timestamp_starts"))

    def test_removed_route_source_timestamp_ends_field(self):
        s = _expected_summary()
        self.assertFalse(hasattr(s, "route_source_timestamp_ends"))

    def test_removed_source_to_fix_delta_mean_us_field(self):
        s = _expected_summary()
        self.assertFalse(hasattr(s, "source_to_fix_delta_mean_us"))

    def test_removed_source_to_fix_delta_median_us_field(self):
        s = _expected_summary()
        self.assertFalse(hasattr(s, "source_to_fix_delta_median_us"))

    def test_removed_source_to_fix_delta_p90_us_field(self):
        s = _expected_summary()
        self.assertFalse(hasattr(s, "source_to_fix_delta_p90_us"))

    def test_frozen(self):
        s = _expected_summary()
        with self.assertRaises(FrozenInstanceError):
            s.outcome = "rejected"


class GroundTruthScenarioManifestV1Tests(unittest.TestCase):
    def test_valid_manifest(self):
        m = _manifest()
        self.assertIsInstance(m, GroundTruthScenarioManifestV1)
        self.assertEqual(m.schema_version, "1.0")
        self.assertEqual(m.record_kind, "ground_truth_scenario")
        self.assertEqual(m.scenario_id, "cyt.synthetic.basic_replay")
        self.assertEqual(m.scenario_version, "1.0")
        self.assertEqual(m.scenario_label, "Basic Replay Test")
        self.assertEqual(m.tags, ("replay", "smoke"))
        self.assertEqual(m.input_manifest_digest, "a" * 64)

    def test_wrong_schema_version_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(schema_version="2.0")

    def test_wrong_record_kind_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(record_kind="wrong_kind")

    def test_invalid_scenario_id_no_dot(self):
        with self.assertRaises(ValueError):
            _manifest(scenario_id="missingdot")

    def test_invalid_scenario_id_uppercase(self):
        with self.assertRaises(ValueError):
            _manifest(scenario_id="Cyt.Uppercase")

    def test_invalid_scenario_id_trailing_dot(self):
        with self.assertRaises(ValueError):
            _manifest(scenario_id="cyt.")

    def test_invalid_scenario_id_leading_dot(self):
        with self.assertRaises(ValueError):
            _manifest(scenario_id=".leading")

    def test_valid_scenario_id_multi_namespace(self):
        m = _manifest(scenario_id="a.b.c")
        self.assertEqual(m.scenario_id, "a.b.c")

    def test_valid_scenario_id_with_digits(self):
        m = _manifest(scenario_id="scenario1.v2_test")
        self.assertEqual(m.scenario_id, "scenario1.v2_test")

    def test_empty_schema_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(scenario_version="")

    def test_empty_label_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(scenario_label="")

    def test_tags_not_sorted_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(tags=("z_tag", "a_tag"))

    def test_tags_duplicates_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(tags=("dup", "dup"))

    def test_tags_not_lowercase_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(tags=("UPPERCASE",))

    def test_tags_with_whitespace_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(tags=("has space",))

    def test_tags_must_be_tuple(self):
        with self.assertRaises(ValueError):
            _manifest(tags=["list", "not_tuple"])

    def test_tags_empty_string_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(tags=("valid", ""))

    def test_tags_invalid_character_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(tags=("tag@invalid",))

    def test_invalid_digest_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(input_manifest_digest="xyz")

    def test_digest_uppercase_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(input_manifest_digest="A" + "a" * 63)

    def test_digest_too_short_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(input_manifest_digest="a" * 63)

    def test_expected_summary_type_check(self):
        with self.assertRaises(ValueError):
            _manifest(expected_summary="not-a-summary")

    def test_frozen(self):
        m = _manifest()
        with self.assertRaises(FrozenInstanceError):
            m.scenario_id = "changed"

    def test_expected_summary_delegation(self):
        es = _expected_summary(
            outcome="rejected",
            rejection_stage="observation_decode",
        )
        m = _manifest(expected_summary=es)
        self.assertEqual(m.expected_summary.outcome, "rejected")
        self.assertEqual(
            m.expected_summary.rejection_stage,
            "observation_decode",
        )


class ConstantsTests(unittest.TestCase):
    def test_schema_version_constant(self):
        self.assertEqual(SCHEMA_VERSION_V1, "1.0")

    def test_record_kind_constant(self):
        self.assertEqual(RECORD_KIND, "ground_truth_scenario")

    def test_rejection_stages_known_set(self):
        expected = {
            "observation_decode",
            "observation_write",
            "operator_fix_decode",
            "correlation_plan",
            "location_link_write",
            "lifecycle_validation",
            "route_construction",
            "result_validation",
        }
        self.assertEqual(REJECTION_STAGES, expected)


if __name__ == "__main__":
    unittest.main()
