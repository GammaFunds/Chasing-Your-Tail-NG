from __future__ import annotations

import unittest

from ground_truth_scenario_contract import GroundTruthExpectedSummaryV1
from ground_truth_summary_builder import (
    build_completed_ground_truth_summary_v1,
)
from observation_contract import (
    ObservationEventV1,
    ObservationLocationLinkV1,
    ObservationProvenanceV1,
)
from observation_location_link_writer import LocationLinkWriteSummaryV1
from route_session_contract import (
    AnalysisSessionV1,
    CollectionSessionCloseV1,
    CollectionSessionV1,
    CollectionSourceMembershipCloseV1,
    CollectionSourceMembershipV1,
    RouteSessionProvenanceV1,
    RouteV1,
)
from synthetic_jsonl_adapter import ReplaySummaryV1


_OBS_PROV = ObservationProvenanceV1(
    collector_name="test.collector",
    collector_version="1.0",
    ingest_mode="replay",
)
_RS_PROV = RouteSessionProvenanceV1(
    controller_name="test.controller",
    controller_version="1.0",
    operation_mode="session_control",
)
_AS_PROV = RouteSessionProvenanceV1(
    controller_name="test.controller",
    controller_version="1.0",
    operation_mode="analysis",
)

_ZERO64 = "0" * 64
_ONE64 = "1" * 64
_TWO64 = "2" * 64

_OBS_0_ID = f"obs_v1_{_ZERO64}"
_OBS_1_ID = f"obs_v1_{_ONE64}"
_OBS_2_ID = f"obs_v1_{_TWO64}"

_LOC_0_ID = f"loc_v1_{_ZERO64}"
_LOC_1_ID = f"loc_v1_{_ONE64}"
_LOC_2_ID = f"loc_v1_{_TWO64}"


def _make_event(
    obs_id: str,
    source_ts: int = 1000,
) -> ObservationEventV1:
    return ObservationEventV1(
        schema_version="1.0",
        record_kind="observation_event",
        observation_id=obs_id,
        collection_session_id="session_1",
        source_type="test.source",
        sensor_id="sensor_1",
        source_timestamp_us=source_ts,
        ingest_timestamp_us=2000,
        source_record_reference=f"ref_{obs_id[-4:]}",
        provenance=_OBS_PROV,
    )


def _make_link(
    loc_id: str,
    obs_id: str,
    delta: int = 0,
) -> ObservationLocationLinkV1:
    return ObservationLocationLinkV1(
        schema_version="1.0",
        record_kind="observation_location_link",
        location_link_id=loc_id,
        observation_id=obs_id,
        operator_fix_id="fix_v1_" + _ZERO64,
        operator_latitude=0.0,
        operator_longitude=0.0,
        operator_fix_timestamp_us=1000,
        source_to_fix_delta_us=delta,
        correlation_method="test.method",
        correlation_version="1.0",
    )


def _make_session() -> CollectionSessionV1:
    return CollectionSessionV1(
        schema_version="1.0",
        record_kind="collection_session",
        collection_session_id="csn_v1_" + _ZERO64,
        session_controller_id="controller_1",
        collection_session_reference="ref_001",
        opened_source_timestamp_us=0,
        time_basis="source_timestamp_us",
        boundary_policy="explicit_half_open_v1",
        ingest_timestamp_us=2000,
        provenance=_RS_PROV,
    )


def _make_membership() -> CollectionSourceMembershipV1:
    return CollectionSourceMembershipV1(
        schema_version="1.0",
        record_kind="collection_source_membership",
        membership_id="csm_v1_" + _ZERO64,
        collection_session_id="session_1",
        source_type="test.source",
        sensor_id="sensor_1",
        source_instance_reference="inst_001",
        joined_source_timestamp_us=0,
        ingest_timestamp_us=2000,
        provenance=_RS_PROV,
    )


def _make_membership_close() -> CollectionSourceMembershipCloseV1:
    return CollectionSourceMembershipCloseV1(
        schema_version="1.0",
        record_kind="collection_source_membership_close",
        membership_close_id="cmc_v1_" + _ZERO64,
        membership_id="csm_v1_" + _ZERO64,
        left_source_timestamp_us=5000,
        close_reason="normal",
        ingest_timestamp_us=6000,
        provenance=_RS_PROV,
    )


def _make_session_close() -> CollectionSessionCloseV1:
    return CollectionSessionCloseV1(
        schema_version="1.0",
        record_kind="collection_session_close",
        session_close_id="csc_v1_" + _ZERO64,
        collection_session_id="session_1",
        closed_source_timestamp_us=5000,
        close_reason="completed",
        ingest_timestamp_us=6000,
        provenance=_RS_PROV,
    )


def _make_route(
    route_id: str,
    point_count: int = 1,
    start_ts: int = 1000,
    end_ts: int = 1000,
) -> RouteV1:
    return RouteV1(
        schema_version="1.0",
        record_kind="route",
        route_id=route_id,
        collection_session_id="session_1",
        route_method="operator_fix_gap_partition",
        route_version="1.0",
        max_internal_gap_us=0,
        ordered_operator_fix_ids=tuple(
            f"fix_v1_{str(i).zfill(64)}" for i in range(point_count)
        ),
        started_source_timestamp_us=start_ts,
        ended_source_timestamp_us=end_ts,
        point_count=point_count,
        created_ingest_timestamp_us=2000,
        provenance=_RS_PROV,
    )


def _make_analysis() -> AnalysisSessionV1:
    return AnalysisSessionV1(
        schema_version="1.0",
        record_kind="analysis_session",
        analysis_session_id="asn_v1_" + _ZERO64,
        analysis_type="ground_truth_review",
        analysis_version="1.0",
        ordered_collection_session_ids=("session_1",),
        ordered_route_ids=(),
        input_manifest_digest=_ZERO64,
        created_ingest_timestamp_us=2000,
        provenance=_AS_PROV,
    )


class TestBuildCompletedGroundTruthSummaryV1(unittest.TestCase):
    def _default_replay(self) -> ReplaySummaryV1:
        return ReplaySummaryV1(
            total_records=1, inserted=1, duplicate=0, identity_conflict=0,
        )

    def _default_link_summary(self) -> LocationLinkWriteSummaryV1:
        return LocationLinkWriteSummaryV1(
            total_candidates=1, inserted=1, duplicate=0, identity_conflict=0,
        )

    def _default_args(self, **overrides):
        args = dict(
            replay_summary=self._default_replay(),
            location_link_write_summary=self._default_link_summary(),
            observations=(_make_event(_OBS_0_ID),),
            location_links=(_make_link(_LOC_0_ID, _OBS_0_ID),),
            collection_sessions=(_make_session(),),
            source_memberships=(_make_membership(),),
            membership_closes=(_make_membership_close(),),
            session_closes=(_make_session_close(),),
            routes=(_make_route("rte_v1_" + _ZERO64),),
            analysis_sessions=(_make_analysis(),),
        )
        args.update(overrides)
        return args

    # --- exact completed summary ---

    def test_exact_completed_summary(self):
        summary = build_completed_ground_truth_summary_v1(
            **self._default_args()
        )
        self.assertEqual(summary.outcome, "completed")
        self.assertIsNone(summary.rejection_stage)
        self.assertEqual(summary.observation_event_count, 1)
        self.assertEqual(summary.observation_location_link_count, 1)
        self.assertEqual(summary.collection_session_count, 1)
        self.assertEqual(summary.source_membership_count, 1)
        self.assertEqual(summary.membership_close_count, 1)
        self.assertEqual(summary.session_close_count, 1)
        self.assertEqual(summary.route_count, 1)
        self.assertEqual(summary.analysis_session_count, 1)
        self.assertEqual(summary.unlinked_observation_count, 0)
        self.assertEqual(summary.route_point_counts, (1,))
        self.assertEqual(
            summary.route_source_time_bounds_us, ((1000, 1000),)
        )
        self.assertEqual(summary.source_to_fix_deltas_us, (0,))

    # --- deterministic route ordering ---

    def test_deterministic_route_ordering(self):
        route_c = _make_route("rte_v1_c" + "0" * 63, point_count=3)
        route_b = _make_route("rte_v1_b" + "0" * 63, point_count=2)
        route_a = _make_route("rte_v1_a" + "0" * 63, point_count=1)
        summary = build_completed_ground_truth_summary_v1(
            **self._default_args(
                routes=(route_c, route_b, route_a),
            )
        )
        self.assertEqual(summary.route_count, 3)
        self.assertEqual(summary.route_point_counts, (1, 2, 3))
        self.assertEqual(
            summary.route_source_time_bounds_us,
            ((1000, 1000), (1000, 1000), (1000, 1000)),
        )

    # --- deterministic link ordering ---

    def test_deterministic_link_ordering(self):
        obs = (
            _make_event(_OBS_0_ID),
            _make_event(_OBS_1_ID),
            _make_event(_OBS_2_ID),
        )
        link_f = _make_link("loc_v1_f" + "0" * 63, _OBS_2_ID, delta=200)
        link_a = _make_link("loc_v1_a" + "0" * 63, _OBS_1_ID, delta=100)
        link_0 = _make_link("loc_v1_" + "0" * 64, _OBS_0_ID, delta=0)
        summary = build_completed_ground_truth_summary_v1(
            **self._default_args(
                observations=obs,
                location_links=(link_f, link_a, link_0),
            )
        )
        self.assertEqual(summary.observation_location_link_count, 3)
        self.assertEqual(summary.source_to_fix_deltas_us, (0, 100, 200))

    # --- signed negative, zero, and positive deltas ---

    def test_signed_deltas(self):
        obs = (_make_event(_OBS_0_ID), _make_event(_OBS_1_ID))
        link_c = _make_link("loc_v1_c" + "0" * 63, _OBS_0_ID, delta=-100)
        link_b = _make_link("loc_v1_b" + "0" * 63, _OBS_1_ID, delta=0)
        link_a = _make_link("loc_v1_a" + "0" * 63, _OBS_0_ID, delta=500)
        summary = build_completed_ground_truth_summary_v1(
            **self._default_args(
                observations=obs,
                location_links=(link_c, link_b, link_a),
            )
        )
        self.assertEqual(
            summary.source_to_fix_deltas_us, (500, 0, -100)
        )

    # --- unlinked observation counting ---

    def test_unlinked_observation_count(self):
        obs = (
            _make_event(_OBS_0_ID),
            _make_event(_OBS_1_ID),
            _make_event(_OBS_2_ID),
        )
        links = (
            _make_link(_LOC_0_ID, _OBS_0_ID),
            _make_link(_LOC_1_ID, _OBS_1_ID),
        )
        summary = build_completed_ground_truth_summary_v1(
            **self._default_args(
                observations=obs,
                location_links=links,
            )
        )
        self.assertEqual(summary.observation_event_count, 3)
        self.assertEqual(summary.observation_location_link_count, 2)
        self.assertEqual(summary.unlinked_observation_count, 1)

    # --- replay count independence from persisted count ---

    def test_replay_count_independence(self):
        replay = ReplaySummaryV1(
            total_records=5,
            inserted=3,
            duplicate=1,
            identity_conflict=1,
        )
        summary = build_completed_ground_truth_summary_v1(
            **self._default_args(replay_summary=replay)
        )
        self.assertEqual(summary.replay_summary.total_records, 5)
        self.assertEqual(summary.replay_summary.inserted, 3)
        self.assertEqual(summary.replay_summary.duplicate, 1)
        self.assertEqual(summary.replay_summary.identity_conflict, 1)
        self.assertEqual(summary.observation_event_count, 1)

    # --- duplicate record-ID rejection ---

    def test_duplicate_observation_id_rejected(self):
        obs = (_make_event(_OBS_0_ID), _make_event(_OBS_0_ID))
        with self.assertRaises(ValueError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(observations=obs)
            )
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_duplicate_link_id_rejected(self):
        links = (_make_link(_LOC_0_ID, _OBS_0_ID), _make_link(_LOC_0_ID, _OBS_0_ID))
        with self.assertRaises(ValueError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(location_links=links)
            )
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_duplicate_session_id_rejected(self):
        s = _make_session()
        with self.assertRaises(ValueError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(collection_sessions=(s, s))
            )
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_duplicate_membership_id_rejected(self):
        m = _make_membership()
        with self.assertRaises(ValueError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(source_memberships=(m, m))
            )
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_duplicate_membership_close_id_rejected(self):
        mc = _make_membership_close()
        with self.assertRaises(ValueError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(membership_closes=(mc, mc))
            )
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_duplicate_session_close_id_rejected(self):
        sc = _make_session_close()
        with self.assertRaises(ValueError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(session_closes=(sc, sc))
            )
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_duplicate_route_id_rejected(self):
        r = _make_route("rte_v1_" + _ZERO64)
        with self.assertRaises(ValueError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(routes=(r, r))
            )
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_duplicate_analysis_session_id_rejected(self):
        a = _make_analysis()
        with self.assertRaises(ValueError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(analysis_sessions=(a, a))
            )
        self.assertIn("duplicate", str(ctx.exception).lower())

    # --- missing parent observation rejection ---

    def test_link_referencing_unknown_observation_rejected(self):
        links = (_make_link(_LOC_0_ID, _OBS_0_ID),)
        with self.assertRaises(ValueError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(
                    observations=(_make_event(_OBS_1_ID),),
                    location_links=links,
                )
            )
        self.assertIn("unknown observation_id", str(ctx.exception))

    def test_link_referencing_nonexistent_observation_rejected(self):
        unknown_obs_id = "obs_v1_" + "f" * 64
        links = (_make_link(_LOC_0_ID, unknown_obs_id),)
        with self.assertRaises(ValueError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(
                    observations=(_make_event(_OBS_0_ID),),
                    location_links=links,
                )
            )
        self.assertIn("unknown observation_id", str(ctx.exception))

    # --- non-tuple rejection ---

    def test_non_tuple_observations_rejected(self):
        with self.assertRaises(TypeError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(observations=[_make_event(_OBS_0_ID)])
            )
        self.assertIn("must be a tuple", str(ctx.exception))

    def test_non_tuple_location_links_rejected(self):
        with self.assertRaises(TypeError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(
                    location_links=[_make_link(_LOC_0_ID, _OBS_0_ID)]
                )
            )
        self.assertIn("must be a tuple", str(ctx.exception))

    def test_non_tuple_collection_sessions_rejected(self):
        with self.assertRaises(TypeError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(
                    collection_sessions=[_make_session()]
                )
            )
        self.assertIn("must be a tuple", str(ctx.exception))

    def test_non_tuple_source_memberships_rejected(self):
        with self.assertRaises(TypeError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(
                    source_memberships=[_make_membership()]
                )
            )
        self.assertIn("must be a tuple", str(ctx.exception))

    def test_non_tuple_routes_rejected(self):
        with self.assertRaises(TypeError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(
                    routes=[_make_route("rte_v1_" + _ZERO64)]
                )
            )
        self.assertIn("must be a tuple", str(ctx.exception))

    # --- wrong element-type rejection ---

    def test_wrong_element_type_in_observations_rejected(self):
        with self.assertRaises(TypeError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(observations=("not_an_event",))
            )
        self.assertIn("observations[0]", str(ctx.exception))

    def test_wrong_element_type_in_location_links_rejected(self):
        with self.assertRaises(TypeError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(location_links=("not_a_link",))
            )
        self.assertIn("location_links[0]", str(ctx.exception))

    def test_wrong_element_type_in_collection_sessions_rejected(self):
        with self.assertRaises(TypeError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(
                    collection_sessions=("not_a_session",)
                )
            )
        self.assertIn("collection_sessions[0]", str(ctx.exception))

    def test_wrong_element_type_in_routes_rejected(self):
        with self.assertRaises(TypeError) as ctx:
            build_completed_ground_truth_summary_v1(
                **self._default_args(routes=("not_a_route",))
            )
        self.assertIn("routes[0]", str(ctx.exception))

    # --- frozen returned summary ---

    def test_returned_summary_is_frozen(self):
        summary = build_completed_ground_truth_summary_v1(
            **self._default_args()
        )
        with self.assertRaises(AttributeError):
            summary.outcome = "rejected"


if __name__ == "__main__":
    unittest.main()
