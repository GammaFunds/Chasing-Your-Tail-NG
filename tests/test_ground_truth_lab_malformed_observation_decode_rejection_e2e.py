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
from observation_location_link_writer import (
    LocationLinkWriteSummaryV1,
)
from observation_store import ObservationStore
from route_session_contract import (
    RouteSessionProvenanceV1,
    create_collection_session,
    create_source_membership,
)
from synthetic_jsonl_adapter import (
    ReplaySummaryV1,
    SyntheticJsonlDecodeError,
    replay_synthetic_jsonl,
)

HMAC_KEY = b"malformed-observation-decode-rejection-e2e-test-key"
SESSION_CONTROLLER_ID = "e2e_controller"
SESSION_REFERENCE = "malformed_observation_decode_rejection_001"
OBS_SENSOR_ID = "obs_sensor"
INGEST_TS = 2_000_000
OBS_SOURCE_TS = 1_000_000

RS_PROV = RouteSessionProvenanceV1(
    controller_name="e2e_controller",
    controller_version="1.0.0",
    operation_mode="session_control",
)

VALID_OBS_LINE = json.dumps(
    {
        "source_record_reference": "obs_001",
        "source_timestamp_us": OBS_SOURCE_TS,
    },
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
)

MALFORMED_OBS_LINE = '{"source_record_reference":'

_DIGEST_INPUT = json.dumps(
    [
        {
            "operation": "replay_synthetic_jsonl",
            "pass_index": 1,
            "lines": [
                VALID_OBS_LINE,
                MALFORMED_OBS_LINE,
            ],
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
    outcome="rejected",
    rejection_stage="observation_decode",
    replay_summary=ReplaySummaryV1(
        total_records=0,
        inserted=0,
        duplicate=0,
        identity_conflict=0,
    ),
    location_link_write_summary=LocationLinkWriteSummaryV1(
        total_candidates=0,
        inserted=0,
        duplicate=0,
        identity_conflict=0,
    ),
    observation_event_count=0,
    observation_location_link_count=0,
    collection_session_count=1,
    source_membership_count=1,
    membership_close_count=0,
    session_close_count=0,
    route_count=0,
    analysis_session_count=0,
    unlinked_observation_count=0,
    route_point_counts=(),
    route_source_time_bounds_us=(),
    source_to_fix_deltas_us=(),
)

MANIFEST = GroundTruthScenarioManifestV1(
    schema_version=SCHEMA_VERSION_V1,
    record_kind=RECORD_KIND,
    scenario_id="cyt.test.malformed_observation_batch_rejected_before_write",
    scenario_version="1.0.0",
    scenario_label="Malformed Observation Batch Rejected Before Write Scenario",
    tags=(
        "decode-before-write",
        "e2e",
        "malformed-input",
        "no-partial-persistence",
    ),
    input_manifest_digest=INPUT_MANIFEST_DIGEST,
    expected_summary=EXPECTED_SUMMARY,
)


class TestMalformedObservationBatchRejectedBeforeWriteE2E(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

    def _open_store(self):
        db_path = Path(self.tempdir.name) / "store.sqlite"
        store = ObservationStore(db_path)
        self.addCleanup(store.close)
        return store

    def test_malformed_observation_batch_rejected_before_write(self):
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

        # --- declare the digest input before replay ---
        self.assertEqual(
            json.dumps(
                [
                    {
                        "operation": "replay_synthetic_jsonl",
                        "pass_index": 1,
                        "lines": [
                            VALID_OBS_LINE,
                            MALFORMED_OBS_LINE,
                        ],
                    },
                ],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            _DIGEST_INPUT,
        )

        # --- replay the malformed batch ---
        with self.assertRaises(SyntheticJsonlDecodeError) as context:
            replay_synthetic_jsonl(
                [VALID_OBS_LINE, MALFORMED_OBS_LINE],
                store=store,
                hmac_key=HMAC_KEY,
                collection_session_id=session.collection_session_id,
                sensor_id=OBS_SENSOR_ID,
                ingest_timestamp_us=INGEST_TS,
            )

        self.assertEqual(str(context.exception), "line 2: malformed JSON")

        # --- prove no partial writes happened ---
        events = store.list_observation_events()
        links = store.list_observation_location_links()
        self.assertEqual(events, ())
        self.assertEqual(links, ())

        # --- build the rejected summary from the observed zero store state ---
        actual_summary = GroundTruthExpectedSummaryV1(
            outcome="rejected",
            rejection_stage="observation_decode",
            replay_summary=ReplaySummaryV1(
                total_records=0,
                inserted=0,
                duplicate=0,
                identity_conflict=0,
            ),
            location_link_write_summary=LocationLinkWriteSummaryV1(
                total_candidates=0,
                inserted=0,
                duplicate=0,
                identity_conflict=0,
            ),
            observation_event_count=len(events),
            observation_location_link_count=len(links),
            collection_session_count=1,
            source_membership_count=1,
            membership_close_count=0,
            session_close_count=0,
            route_count=0,
            analysis_session_count=0,
            unlinked_observation_count=0,
            route_point_counts=(),
            route_source_time_bounds_us=(),
            source_to_fix_deltas_us=(),
        )

        self.assertEqual(actual_summary, MANIFEST.expected_summary)
