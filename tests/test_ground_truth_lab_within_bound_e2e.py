from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
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
    validate_source_membership_boundaries,
    validate_source_record_admission,
)
from synthetic_jsonl_adapter import ReplaySummaryV1, replay_synthetic_jsonl
from synthetic_operator_fix_jsonl_adapter import (
    decode_synthetic_operator_fix_jsonl,
)

HMAC_KEY = b"within-bound-e2e-test-key"
SESSION_CONTROLLER_ID = "e2e_controller"
SESSION_REFERENCE = "within_bound_001"
OBS_SENSOR_ID = "obs_sensor"
GPS_SENSOR_ID = "gps_sensor"
INGEST_TS = 2_000_000
OBS_SOURCE_TS = 1_000_000
FIX_SOURCE_TS = 1_000_250
CORRELATION_BOUND_US = 500

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

OBS_LINE = json.dumps(
    {"source_record_reference": "obs_001", "source_timestamp_us": OBS_SOURCE_TS},
    separators=(",", ":"),
    sort_keys=True,
)

FIX_LINE = json.dumps(
    {
        "source_record_reference": "fix_001",
        "operator_fix_timestamp_us": FIX_SOURCE_TS,
        "operator_latitude": 0,
        "operator_longitude": 0,
    },
    separators=(",", ":"),
    sort_keys=True,
)

_DIGEST_INPUT = json.dumps(
    [
        {"source_record_reference": "obs_001", "source_timestamp_us": OBS_SOURCE_TS},
        {
            "source_record_reference": "fix_001",
            "operator_fix_timestamp_us": FIX_SOURCE_TS,
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
        total_records=1, inserted=1, duplicate=0, identity_conflict=0,
    ),
    location_link_write_summary=LocationLinkWriteSummaryV1(
        total_candidates=1, inserted=1, duplicate=0, identity_conflict=0,
    ),
    observation_event_count=1,
    observation_location_link_count=1,
    collection_session_count=1,
    source_membership_count=1,
    membership_close_count=1,
    session_close_count=1,
    route_count=1,
    analysis_session_count=1,
    unlinked_observation_count=0,
    route_point_counts=(1,),
    route_source_time_bounds_us=((FIX_SOURCE_TS, FIX_SOURCE_TS),),
    source_to_fix_deltas_us=(250,),
)

MANIFEST = GroundTruthScenarioManifestV1(
    schema_version=SCHEMA_VERSION_V1,
    record_kind=RECORD_KIND,
    scenario_id="cyt.test.positive_delta_within_bound",
    scenario_version="1.0.0",
    scenario_label="Positive Delta Strictly Within Bound Scenario",
    tags=("e2e", "within-bound"),
    input_manifest_digest=INPUT_MANIFEST_DIGEST,
    expected_summary=EXPECTED_SUMMARY,
)


class TestPositiveDeltaStrictlyWithinBoundMatchesManifest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

    def _open_store(self):
        db_path = Path(self.tempdir.name) / "store.sqlite"
        store = ObservationStore(db_path)
        self.addCleanup(store.close)
        return store

    def test_positive_delta_strictly_within_bound_matches_manifest(self):
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
            opened_source_timestamp_us=0,
            ingest_timestamp_us=INGEST_TS,
            provenance=RS_PROV,
        )

        # --- source membership ---
        membership = create_source_membership(
            hmac_key=HMAC_KEY,
            collection_session=session,
            source_type="synthetic.jsonl",
            sensor_id=OBS_SENSOR_ID,
            source_instance_reference="obs_instance_001",
            joined_source_timestamp_us=0,
            ingest_timestamp_us=INGEST_TS,
            provenance=RS_PROV,
        )

        # --- replay one observation ---
        replay_summary = replay_synthetic_jsonl(
            [OBS_LINE],
            store=store,
            hmac_key=HMAC_KEY,
            collection_session_id=session.collection_session_id,
            sensor_id=OBS_SENSOR_ID,
            ingest_timestamp_us=INGEST_TS,
        )

        # --- decode one operator fix ---
        fixes = decode_synthetic_operator_fix_jsonl(
            [FIX_LINE],
            hmac_key=HMAC_KEY,
            collection_session_id=session.collection_session_id,
            sensor_id=GPS_SENSOR_ID,
            ingest_timestamp_us=INGEST_TS,
        )
        fix = fixes[0]

        # --- run bounded correlation orchestrator ---
        link_summary = run_bounded_observation_location_link_correlation(
            store=store,
            hmac_key=HMAC_KEY,
            operator_fixes=fixes,
            max_delta_us=CORRELATION_BOUND_US,
            collection_session_id=session.collection_session_id,
        )

        # --- close records (after observation/fix timestamp) ---
        membership_close = create_membership_close(
            hmac_key=HMAC_KEY,
            membership=membership,
            left_source_timestamp_us=2_000_000,
            close_reason="normal",
            ingest_timestamp_us=INGEST_TS,
            provenance=RS_PROV,
        )

        session_close = create_session_close(
            hmac_key=HMAC_KEY,
            collection_session=session,
            closed_source_timestamp_us=2_000_000,
            close_reason="completed",
            ingest_timestamp_us=INGEST_TS,
            provenance=RS_PROV,
        )

        # --- validate source-record admission ---
        validate_source_record_admission(
            session,
            membership,
            OBS_SOURCE_TS,
            session_close=session_close,
            membership_close=membership_close,
        )

        # --- validate lifecycle boundaries ---
        validate_collection_session_boundaries(
            session, session_close=session_close,
        )
        validate_source_membership_boundaries(
            membership, membership_close=membership_close,
        )

        # --- create route from decoded fix ---
        route = create_route(
            hmac_key=HMAC_KEY,
            collection_session_id=session.collection_session_id,
            operator_fixes=[fix],
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
        events = store.list_observation_events()
        links = store.list_observation_location_links()

        actual_summary = build_completed_ground_truth_summary_v1(
            replay_summary=replay_summary,
            location_link_write_summary=link_summary,
            observations=events,
            location_links=links,
            collection_sessions=(session,),
            source_memberships=(membership,),
            membership_closes=(membership_close,),
            session_closes=(session_close,),
            routes=(route,),
            analysis_sessions=(analysis_session,),
        )

        # --- assert exact equality with manifest ---
        self.assertEqual(actual_summary, MANIFEST.expected_summary)

        # --- additional assertions ---
        obs = events[0]
        self.assertEqual(
            obs.collection_session_id,
            session.collection_session_id,
        )
        self.assertEqual(
            fix.collection_session_id,
            session.collection_session_id,
        )

        link = links[0]
        self.assertEqual(link.observation_id, obs.observation_id)
        self.assertEqual(link.source_to_fix_delta_us, 250)
        self.assertLess(abs(link.source_to_fix_delta_us), 500)

        self.assertEqual(route.started_source_timestamp_us, FIX_SOURCE_TS)
        self.assertEqual(route.ended_source_timestamp_us, FIX_SOURCE_TS)
        self.assertEqual(route.point_count, 1)

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
