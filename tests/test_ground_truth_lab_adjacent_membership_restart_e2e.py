from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ground_truth_scenario_contract import (
    GroundTruthExpectedSummaryV1,
    GroundTruthScenarioManifestV1,
    RECORD_KIND,
    SCHEMA_VERSION_V1,
)
from ground_truth_summary_builder import (
    build_completed_ground_truth_summary_v1,
)
from observation_location_link_orchestrator import (
    run_bounded_observation_location_link_correlation,
)
from observation_location_link_writer import (
    LocationLinkWriteSummaryV1,
)
from observation_store import ObservationStore
from route_session_contract import (
    AnalysisSessionV1,
    CollectionSessionCloseV1,
    CollectionSessionV1,
    CollectionSourceMembershipCloseV1,
    CollectionSourceMembershipV1,
    RouteSessionProvenanceV1,
    RouteV1,
    create_analysis_session,
    create_collection_session,
    create_membership_close,
    create_route,
    create_session_close,
    create_source_membership,
    validate_collection_session_boundaries,
    validate_no_membership_overlap,
    validate_source_membership_boundaries,
    validate_source_record_admission,
)
from synthetic_jsonl_adapter import ReplaySummaryV1, replay_synthetic_jsonl
from synthetic_operator_fix_jsonl_adapter import (
    decode_synthetic_operator_fix_jsonl,
)

HMAC_KEY = b"adjacent-membership-restart-e2e-test-key"
SESSION_CONTROLLER_ID = "e2e_controller"
SESSION_REFERENCE = "adjacent_membership_restart_001"
OBS_SENSOR_ID = "obs_sensor"
GPS_SENSOR_ID = "gps_sensor"

SESSION_OPEN_TS = 1_000_000
MEMBERSHIP_RESTART_TS = 2_000_000
SESSION_CLOSE_TS = 3_000_000
OBS_BEFORE_TS = 1_999_999
OBS_AFTER_TS = 2_000_000
FIX_BEFORE_TS = 1_999_999
FIX_AFTER_TS = 2_000_000
INGEST_TS = 4_000_000
CORRELATION_BOUND_US = 0
ROUTE_MAX_GAP_US = 10

RS_PROV = RouteSessionProvenanceV1(
    controller_name="e2e_controller",
    controller_version="1.0.0",
    operation_mode="session_control",
)

AS_PROV = RouteSessionProvenanceV1(
    controller_name="e2e_controller",
    controller_version="1.0.0",
    operation_mode="analysis",
)

OBS_BEFORE_LINE = json.dumps(
    {"source_record_reference": "obs_before", "source_timestamp_us": OBS_BEFORE_TS},
    separators=(",", ":"),
    sort_keys=True,
)

OBS_AFTER_LINE = json.dumps(
    {"source_record_reference": "obs_after", "source_timestamp_us": OBS_AFTER_TS},
    separators=(",", ":"),
    sort_keys=True,
)

FIX_BEFORE_LINE = json.dumps(
    {
        "source_record_reference": "fix_before",
        "operator_fix_timestamp_us": FIX_BEFORE_TS,
        "operator_latitude": 0,
        "operator_longitude": 0,
    },
    separators=(",", ":"),
    sort_keys=True,
)

FIX_AFTER_LINE = json.dumps(
    {
        "source_record_reference": "fix_after",
        "operator_fix_timestamp_us": FIX_AFTER_TS,
        "operator_latitude": 0,
        "operator_longitude": 0,
    },
    separators=(",", ":"),
    sort_keys=True,
)

_DIGEST_INPUT = json.dumps(
    [
        {"source_record_reference": "obs_before", "source_timestamp_us": OBS_BEFORE_TS},
        {"source_record_reference": "obs_after", "source_timestamp_us": OBS_AFTER_TS},
        {
            "source_record_reference": "fix_before",
            "operator_fix_timestamp_us": FIX_BEFORE_TS,
            "operator_latitude": 0,
            "operator_longitude": 0,
        },
        {
            "source_record_reference": "fix_after",
            "operator_fix_timestamp_us": FIX_AFTER_TS,
            "operator_latitude": 0,
            "operator_longitude": 0,
        },
    ],
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
)
INPUT_MANIFEST_DIGEST = hashlib.sha256(
    _DIGEST_INPUT.encode("utf-8")
).hexdigest()

EXPECTED_SUMMARY = GroundTruthExpectedSummaryV1(
    outcome="completed",
    rejection_stage=None,
    replay_summary=ReplaySummaryV1(
        total_records=2, inserted=2, duplicate=0, identity_conflict=0,
    ),
    location_link_write_summary=LocationLinkWriteSummaryV1(
        total_candidates=2, inserted=2, duplicate=0, identity_conflict=0,
    ),
    observation_event_count=2,
    observation_location_link_count=2,
    collection_session_count=1,
    source_membership_count=2,
    membership_close_count=2,
    session_close_count=1,
    route_count=1,
    analysis_session_count=1,
    unlinked_observation_count=0,
    route_point_counts=(2,),
    route_source_time_bounds_us=((FIX_BEFORE_TS, FIX_AFTER_TS),),
    source_to_fix_deltas_us=(0, 0),
)

MANIFEST = GroundTruthScenarioManifestV1(
    schema_version=SCHEMA_VERSION_V1,
    record_kind=RECORD_KIND,
    scenario_id="cyt.test.adjacent_source_membership_restart",
    scenario_version="1.0.0",
    scenario_label="Adjacent Source Membership Restart Scenario",
    tags=("adjacent-memberships", "e2e", "source-restart"),
    input_manifest_digest=INPUT_MANIFEST_DIGEST,
    expected_summary=EXPECTED_SUMMARY,
)


class TestAdjacentSourceMembershipRestartE2E(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

    def _open_store(self):
        db_path = Path(self.tempdir.name) / "store.sqlite"
        store = ObservationStore(db_path)
        self.addCleanup(store.close)
        return store

    def test_adjacent_source_membership_restart_e2e(self):
        # --- pre-declared manifest checks ---
        self.assertEqual(MANIFEST.schema_version, "1.0")
        self.assertEqual(MANIFEST.record_kind, "ground_truth_scenario")
        self.assertRegex(
            MANIFEST.input_manifest_digest,
            r"^[0-9a-f]{64}$",
        )

        # --- create store ---
        store = self._open_store()

        # --- collection session ---
        session = create_collection_session(
            hmac_key=HMAC_KEY,
            session_controller_id=SESSION_CONTROLLER_ID,
            collection_session_reference=SESSION_REFERENCE,
            opened_source_timestamp_us=SESSION_OPEN_TS,
            ingest_timestamp_us=INGEST_TS,
            provenance=RS_PROV,
        )

        # --- source membership before restart ---
        membership_before = create_source_membership(
            hmac_key=HMAC_KEY,
            collection_session=session,
            source_type="synthetic.jsonl",
            sensor_id=OBS_SENSOR_ID,
            source_instance_reference="obs_instance_before_restart",
            joined_source_timestamp_us=SESSION_OPEN_TS,
            ingest_timestamp_us=INGEST_TS,
            provenance=RS_PROV,
        )

        # --- source membership after restart ---
        membership_after = create_source_membership(
            hmac_key=HMAC_KEY,
            collection_session=session,
            source_type="synthetic.jsonl",
            sensor_id=OBS_SENSOR_ID,
            source_instance_reference="obs_instance_after_restart",
            joined_source_timestamp_us=MEMBERSHIP_RESTART_TS,
            ingest_timestamp_us=INGEST_TS,
            provenance=RS_PROV,
        )

        # --- membership invariants ---
        self.assertNotEqual(
            membership_before.membership_id,
            membership_after.membership_id,
        )
        self.assertEqual(
            membership_before.collection_session_id,
            membership_after.collection_session_id,
        )
        self.assertEqual(
            membership_before.source_type,
            membership_after.source_type,
        )
        self.assertEqual(
            membership_before.sensor_id,
            membership_after.sensor_id,
        )

        # --- membership closes and session close ---
        membership_before_close = create_membership_close(
            hmac_key=HMAC_KEY,
            membership=membership_before,
            left_source_timestamp_us=MEMBERSHIP_RESTART_TS,
            close_reason="source_restart",
            ingest_timestamp_us=INGEST_TS,
            provenance=RS_PROV,
        )

        membership_after_close = create_membership_close(
            hmac_key=HMAC_KEY,
            membership=membership_after,
            left_source_timestamp_us=SESSION_CLOSE_TS,
            close_reason="session_closed",
            ingest_timestamp_us=INGEST_TS,
            provenance=RS_PROV,
        )

        self.assertNotEqual(
            membership_before_close.membership_close_id,
            membership_after_close.membership_close_id,
        )

        session_close = create_session_close(
            hmac_key=HMAC_KEY,
            collection_session=session,
            closed_source_timestamp_us=SESSION_CLOSE_TS,
            close_reason="completed",
            ingest_timestamp_us=INGEST_TS,
            provenance=RS_PROV,
        )

        # --- validate adjacent boundary equality ---
        self.assertEqual(
            membership_before_close.left_source_timestamp_us,
            MEMBERSHIP_RESTART_TS,
        )
        self.assertEqual(
            membership_after.joined_source_timestamp_us,
            MEMBERSHIP_RESTART_TS,
        )
        self.assertEqual(
            membership_before_close.left_source_timestamp_us,
            membership_after.joined_source_timestamp_us,
        )

        # --- replay two observations ---
        replay_summary = replay_synthetic_jsonl(
            [OBS_BEFORE_LINE, OBS_AFTER_LINE],
            store=store,
            hmac_key=HMAC_KEY,
            collection_session_id=session.collection_session_id,
            sensor_id=OBS_SENSOR_ID,
            ingest_timestamp_us=INGEST_TS,
        )

        # --- validate admission: obs_before accepted by first membership ---
        validate_source_record_admission(
            session,
            membership_before,
            OBS_BEFORE_TS,
            session_close=session_close,
            membership_close=membership_before_close,
        )

        # --- validate admission: obs_after accepted by second membership ---
        validate_source_record_admission(
            session,
            membership_after,
            OBS_AFTER_TS,
            session_close=session_close,
            membership_close=membership_after_close,
        )

        # --- validate admission: obs_after rejected by first membership
        #     (half-open boundary at MEMBERSHIP_RESTART_TS) ---
        with self.assertRaises(ValueError):
            validate_source_record_admission(
                session,
                membership_before,
                OBS_AFTER_TS,
                session_close=session_close,
                membership_close=membership_before_close,
            )

        # --- validate admission: obs_before rejected by second membership
        #     (precedes join at MEMBERSHIP_RESTART_TS) ---
        with self.assertRaises(ValueError):
            validate_source_record_admission(
                session,
                membership_after,
                OBS_BEFORE_TS,
                session_close=session_close,
                membership_close=membership_after_close,
            )

        # --- decode two transient operator fixes ---
        fixes = decode_synthetic_operator_fix_jsonl(
            [FIX_BEFORE_LINE, FIX_AFTER_LINE],
            hmac_key=HMAC_KEY,
            collection_session_id=session.collection_session_id,
            sensor_id=GPS_SENSOR_ID,
            ingest_timestamp_us=INGEST_TS,
        )
        fix_before, fix_after = fixes

        # --- run bounded correlation orchestrator with both fixes ---
        link_summary = run_bounded_observation_location_link_correlation(
            store=store,
            hmac_key=HMAC_KEY,
            operator_fixes=fixes,
            max_delta_us=CORRELATION_BOUND_US,
            collection_session_id=session.collection_session_id,
        )

        # --- validate links ---
        events = store.list_observation_events()
        links = store.list_observation_location_links()

        obs_by_ts = {e.source_timestamp_us: e for e in events}
        links_by_obs_id = {l.observation_id: l for l in links}

        link_before = links_by_obs_id[
            obs_by_ts[OBS_BEFORE_TS].observation_id
        ]
        link_after = links_by_obs_id[
            obs_by_ts[OBS_AFTER_TS].observation_id
        ]

        self.assertEqual(
            link_before.operator_fix_id,
            fix_before.operator_fix_id,
        )
        self.assertEqual(
            link_after.operator_fix_id,
            fix_after.operator_fix_id,
        )
        self.assertEqual(link_before.source_to_fix_delta_us, 0)
        self.assertEqual(link_after.source_to_fix_delta_us, 0)

        # --- validate lifecycle boundaries ---
        validate_collection_session_boundaries(
            session, session_close=session_close,
        )
        validate_source_membership_boundaries(
            membership_before,
            membership_close=membership_before_close,
            session_collection_session_id=session.collection_session_id,
        )
        validate_source_membership_boundaries(
            membership_after,
            membership_close=membership_after_close,
            session_collection_session_id=session.collection_session_id,
        )

        # --- validate no membership overlap ---
        validate_no_membership_overlap([
            (membership_before, membership_before_close),
            (membership_after, membership_after_close),
        ])

        # --- create route from both decoded fixes ---
        route = create_route(
            hmac_key=HMAC_KEY,
            collection_session_id=session.collection_session_id,
            operator_fixes=[fix_before, fix_after],
            max_internal_gap_us=ROUTE_MAX_GAP_US,
            provenance=RouteSessionProvenanceV1(
                controller_name="e2e_controller",
                controller_version="1.0.0",
                operation_mode="route_snapshot",
            ),
            created_ingest_timestamp_us=INGEST_TS,
        )

        # --- create analysis session ---
        analysis_session = create_analysis_session(
            hmac_key=HMAC_KEY,
            analysis_type="ground_truth_review",
            analysis_version="1.0",
            collection_session_ids=[session.collection_session_id],
            route_ids=[route.route_id],
            input_manifest_digest=INPUT_MANIFEST_DIGEST,
            provenance=AS_PROV,
            created_ingest_timestamp_us=INGEST_TS,
        )

        # --- actual summary from returned summaries, persisted store reads,
        #     and created lifecycle/route/analysis objects ---
        actual_summary = build_completed_ground_truth_summary_v1(
            replay_summary=replay_summary,
            location_link_write_summary=link_summary,
            observations=events,
            location_links=links,
            collection_sessions=(session,),
            source_memberships=(membership_before, membership_after),
            membership_closes=(
                membership_before_close,
                membership_after_close,
            ),
            session_closes=(session_close,),
            routes=(route,),
            analysis_sessions=(analysis_session,),
        )

        # --- assert exact equality with manifest ---
        self.assertEqual(actual_summary, MANIFEST.expected_summary)

        # --- additional assertions ---
        self.assertEqual(
            events[0].collection_session_id,
            session.collection_session_id,
        )
        self.assertEqual(
            events[1].collection_session_id,
            session.collection_session_id,
        )
        self.assertEqual(
            fix_before.collection_session_id,
            session.collection_session_id,
        )
        self.assertEqual(
            fix_after.collection_session_id,
            session.collection_session_id,
        )

        self.assertEqual(route.point_count, 2)
        self.assertEqual(
            route.started_source_timestamp_us,
            FIX_BEFORE_TS,
        )
        self.assertEqual(
            route.ended_source_timestamp_us,
            FIX_AFTER_TS,
        )
        self.assertEqual(
            route.ordered_operator_fix_ids,
            (fix_before.operator_fix_id, fix_after.operator_fix_id),
        )

        self.assertEqual(
            analysis_session.ordered_collection_session_ids,
            (session.collection_session_id,),
        )
        self.assertEqual(
            analysis_session.ordered_route_ids,
            (route.route_id,),
        )

        self.assertRegex(
            MANIFEST.input_manifest_digest,
            r"^[0-9a-f]{64}$",
        )
