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
    create_session_close,
    create_source_membership,
    validate_collection_session_boundaries,
    validate_source_membership_boundaries,
    validate_source_record_admission,
)
from synthetic_jsonl_adapter import (
    ReplaySummaryV1,
    decode_synthetic_jsonl,
    replay_synthetic_jsonl,
)

HMAC_KEY = b"immutable-fact-identity-conflict-e2e-test-key"
SESSION_CONTROLLER_ID = "e2e_controller"
SESSION_REFERENCE = "immutable_fact_conflict_001"
OBS_SENSOR_ID = "obs_sensor"
INGEST_TS_1 = 2_000_000
INGEST_TS_2 = 3_000_000
OBS_SOURCE_TS = 1_000_000
MAX_DELTA_US = 0

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

FIRST_OBS_LINE = json.dumps(
    {
        "source_record_reference": "obs_001",
        "source_timestamp_us": OBS_SOURCE_TS,
        "signal_strength": -10,
        "signal_strength_unit": "synthetic_unit",
    },
    separators=(",", ":"),
    sort_keys=True,
)

CONFLICT_OBS_LINE = json.dumps(
    {
        "source_record_reference": "obs_001",
        "source_timestamp_us": OBS_SOURCE_TS,
        "signal_strength": -20,
        "signal_strength_unit": "synthetic_unit",
    },
    separators=(",", ":"),
    sort_keys=True,
)

_DIGEST_INPUT = json.dumps(
    [
        {
            "operation": "replay_synthetic_jsonl",
            "pass_index": 1,
            "records": [
                {
                    "source_record_reference": "obs_001",
                    "source_timestamp_us": OBS_SOURCE_TS,
                    "signal_strength": -10,
                    "signal_strength_unit": "synthetic_unit",
                }
            ],
        },
        {
            "operation": "replay_synthetic_jsonl",
            "pass_index": 2,
            "records": [
                {
                    "source_record_reference": "obs_001",
                    "source_timestamp_us": OBS_SOURCE_TS,
                    "signal_strength": -20,
                    "signal_strength_unit": "synthetic_unit",
                }
            ],
        },
        {
            "operation": "run_bounded_observation_location_link_correlation",
            "pass_index": 1,
            "max_delta_us": MAX_DELTA_US,
            "operator_fixes": [],
        },
    ],
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
)
INPUT_MANIFEST_DIGEST = hashlib.sha256(
    _DIGEST_INPUT.encode("utf-8")
).hexdigest()

SECOND_REPLAY_SUMMARY = ReplaySummaryV1(
    total_records=1, inserted=0, duplicate=0, identity_conflict=1,
)

EXPECTED_SUMMARY = GroundTruthExpectedSummaryV1(
    outcome="completed",
    rejection_stage=None,
    replay_summary=SECOND_REPLAY_SUMMARY,
    location_link_write_summary=LocationLinkWriteSummaryV1(
        total_candidates=0, inserted=0, duplicate=0, identity_conflict=0,
    ),
    observation_event_count=1,
    observation_location_link_count=0,
    collection_session_count=1,
    source_membership_count=1,
    membership_close_count=1,
    session_close_count=1,
    route_count=0,
    analysis_session_count=1,
    unlinked_observation_count=1,
    route_point_counts=(),
    route_source_time_bounds_us=(),
    source_to_fix_deltas_us=(),
)

MANIFEST = GroundTruthScenarioManifestV1(
    schema_version=SCHEMA_VERSION_V1,
    record_kind=RECORD_KIND,
    scenario_id="cyt.test.changed_immutable_fact_is_identity_conflict",
    scenario_version="1.0.0",
    scenario_label="Changed Immutable Fact Identity Conflict Scenario",
    tags=("e2e", "identity-conflict", "immutable-fact"),
    input_manifest_digest=INPUT_MANIFEST_DIGEST,
    expected_summary=EXPECTED_SUMMARY,
)


class TestImmutableFactIdentityConflictE2E(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

    def _open_store(self):
        db_path = Path(self.tempdir.name) / "store.sqlite"
        store = ObservationStore(db_path)
        self.addCleanup(store.close)
        return store

    def test_immutable_fact_identity_conflict_e2e(self):
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
            ingest_timestamp_us=INGEST_TS_1,
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
            ingest_timestamp_us=INGEST_TS_1,
            provenance=RS_PROV,
        )

        # --- decode both candidate events for comparison (before replay) ---
        first_candidate_events = decode_synthetic_jsonl(
            [FIRST_OBS_LINE],
            hmac_key=HMAC_KEY,
            collection_session_id=session.collection_session_id,
            sensor_id=OBS_SENSOR_ID,
            ingest_timestamp_us=INGEST_TS_1,
        )
        conflict_candidate_events = decode_synthetic_jsonl(
            [CONFLICT_OBS_LINE],
            hmac_key=HMAC_KEY,
            collection_session_id=session.collection_session_id,
            sensor_id=OBS_SENSOR_ID,
            ingest_timestamp_us=INGEST_TS_2,
        )
        first_candidate = first_candidate_events[0]
        conflict_candidate = conflict_candidate_events[0]

        # --- prove same observation_id but different signal_strength ---
        self.assertEqual(
            first_candidate.observation_id,
            conflict_candidate.observation_id,
        )
        self.assertNotEqual(
            first_candidate.signal_strength,
            conflict_candidate.signal_strength,
        )

        # --- FIRST REPLAY: first pass (inserted) ---
        first_replay_summary = replay_synthetic_jsonl(
            [FIRST_OBS_LINE],
            store=store,
            hmac_key=HMAC_KEY,
            collection_session_id=session.collection_session_id,
            sensor_id=OBS_SENSOR_ID,
            ingest_timestamp_us=INGEST_TS_1,
        )

        # --- assert first replay summary separately ---
        self.assertEqual(
            first_replay_summary,
            ReplaySummaryV1(
                total_records=1, inserted=1, duplicate=0, identity_conflict=0,
            ),
        )

        # --- capture state after first replay ---
        events_after_first = store.list_observation_events()
        self.assertEqual(len(events_after_first), 1)
        first_obs_id = events_after_first[0].observation_id

        # --- SECOND REPLAY: conflicting payload (identity_conflict) ---
        second_replay_summary = replay_synthetic_jsonl(
            [CONFLICT_OBS_LINE],
            store=store,
            hmac_key=HMAC_KEY,
            collection_session_id=session.collection_session_id,
            sensor_id=OBS_SENSOR_ID,
            ingest_timestamp_us=INGEST_TS_2,
        )

        # --- assert second replay summary exactly ---
        self.assertEqual(second_replay_summary, SECOND_REPLAY_SUMMARY)

        # --- empty bounded correlation (zero candidates) ---
        link_summary = run_bounded_observation_location_link_correlation(
            store=store,
            hmac_key=HMAC_KEY,
            operator_fixes=(),
            max_delta_us=MAX_DELTA_US,
            collection_session_id=session.collection_session_id,
        )

        # --- close records ---
        membership_close = create_membership_close(
            hmac_key=HMAC_KEY,
            membership=membership,
            left_source_timestamp_us=2_000_000,
            close_reason="normal",
            ingest_timestamp_us=INGEST_TS_2,
            provenance=RS_PROV,
        )

        session_close = create_session_close(
            hmac_key=HMAC_KEY,
            collection_session=session,
            closed_source_timestamp_us=2_000_000,
            close_reason="completed",
            ingest_timestamp_us=INGEST_TS_2,
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
            membership,
            membership_close=membership_close,
            session_collection_session_id=session.collection_session_id,
        )

        # --- no create_route call (no operator fixes) ---

        # --- create analysis session with no routes ---
        analysis_session = create_analysis_session(
            hmac_key=HMAC_KEY,
            analysis_type="ground_truth_review",
            analysis_version="1.0",
            collection_session_ids=[session.collection_session_id],
            route_ids=[],
            input_manifest_digest=INPUT_MANIFEST_DIGEST,
            provenance=AS_PROV,
            created_ingest_timestamp_us=INGEST_TS_2,
        )

        # --- final persisted state ---
        events_final = store.list_observation_events()
        links_final = store.list_observation_location_links()

        # --- build actual summary using second-pass summaries ---
        actual_summary = build_completed_ground_truth_summary_v1(
            replay_summary=second_replay_summary,
            location_link_write_summary=link_summary,
            observations=events_final,
            location_links=links_final,
            collection_sessions=(session,),
            source_memberships=(membership,),
            membership_closes=(membership_close,),
            session_closes=(session_close,),
            routes=(),
            analysis_sessions=(analysis_session,),
        )

        # --- assert exact equality with manifest ---
        self.assertEqual(actual_summary, MANIFEST.expected_summary)

        # --- additional assertions ---
        # After the conflicting replay, persisted state is unchanged
        self.assertEqual(events_final, events_after_first)
        self.assertEqual(len(events_final), 1)

        # observation_id remains stable
        self.assertEqual(events_final[0].observation_id, first_obs_id)

        # stored signal_strength remains -10 (original first-pass value)
        self.assertEqual(events_final[0].signal_strength, -10)
        self.assertEqual(events_final[0].signal_strength_unit, "synthetic_unit")

        # ingest_timestamp_us remains the original first-pass value
        self.assertEqual(events_final[0].ingest_timestamp_us, INGEST_TS_1)

        # no location links
        self.assertEqual(links_final, ())

        self.assertEqual(
            analysis_session.ordered_collection_session_ids,
            (session.collection_session_id,),
        )
        self.assertEqual(
            analysis_session.ordered_route_ids,
            (),
        )

        self.assertRegex(
            MANIFEST.input_manifest_digest,
            r"^[0-9a-f]{64}$",
        )
