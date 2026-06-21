from dataclasses import FrozenInstanceError
import unittest

from observation_contract import (
    ObservationProvenanceV1,
    OperatorFixV1,
    create_operator_fix,
)

from route_session_contract import (
    AnalysisSessionV1,
    CollectionSessionCloseV1,
    CollectionSessionV1,
    CollectionSourceMembershipCloseV1,
    CollectionSourceMembershipV1,
    RouteSessionProvenanceV1,
    RouteV1,
    compare_analysis_session_source_facts,
    compare_collection_session_source_facts,
    compare_membership_close_source_facts,
    compare_route_source_facts,
    compare_session_close_source_facts,
    compare_source_membership_source_facts,
    create_analysis_session,
    create_collection_session,
    create_membership_close,
    create_route,
    create_session_close,
    create_source_membership,
    validate_collection_session_boundaries,
    validate_source_membership_boundaries,
    validate_source_record_admission,
    validate_no_membership_overlap,
    validate_route_fix_inputs,
)

OBSERVATION_KEY = b"synthetic-observation-test-key"
ROUTE_KEY = b"synthetic-route-contract-test-key"


def _obs_prov(**kw):
    vals = {
        "collector_name": "test_collector",
        "collector_version": "1.0",
        "ingest_mode": "live",
        "source_schema_version": "v1",
    }
    vals.update(kw)
    return ObservationProvenanceV1(**vals)


def _fix(**kw):
    vals = {
        "hmac_key": OBSERVATION_KEY,
        "collection_session_id": "csn_v1_" + "a" * 64,
        "source_type": "synthetic.gps",
        "sensor_id": "sensor_alpha",
        "operator_fix_timestamp_us": 1_000_000,
        "ingest_timestamp_us": 1_000_100,
        "source_record_reference": "fix_ref_001",
        "provenance": _obs_prov(),
        "operator_latitude": 33.0,
        "operator_longitude": -112.0,
        "operator_location_accuracy_m": 5.0,
    }
    vals.update(kw)
    return create_operator_fix(**vals)


class RouteSessionProvenanceV1Tests(unittest.TestCase):
    @staticmethod
    def prov(**kw):
        vals = {
            "controller_name": "test_controller",
            "controller_version": "1.0.0",
            "operation_mode": "session_control",
        }
        vals.update(kw)
        return RouteSessionProvenanceV1(**vals)

    def test_valid_provenance(self):
        p = self.prov()
        self.assertIsInstance(p, RouteSessionProvenanceV1)
        self.assertEqual(p.controller_name, "test_controller")
        self.assertEqual(p.controller_version, "1.0.0")
        self.assertEqual(p.operation_mode, "session_control")

    def test_allowed_operation_modes(self):
        for mode in ("session_control", "route_snapshot", "analysis"):
            with self.subTest(mode=mode):
                p = self.prov(operation_mode=mode)
                self.assertEqual(p.operation_mode, mode)

    def test_rejects_invalid_operation_mode(self):
        with self.assertRaises(ValueError):
            self.prov(operation_mode="invalid_mode")

    def test_rejects_empty_controller_name(self):
        with self.assertRaises(ValueError):
            self.prov(controller_name="")

    def test_rejects_empty_controller_version(self):
        with self.assertRaises(ValueError):
            self.prov(controller_version="")

    def test_provenance_is_frozen(self):
        p = self.prov()
        with self.assertRaises(FrozenInstanceError):
            p.controller_name = "changed"


class CollectionSessionV1Tests(unittest.TestCase):
    @staticmethod
    def prov(**kw):
        vals = {
            "controller_name": "test_controller",
            "controller_version": "1.0.0",
            "operation_mode": "session_control",
        }
        vals.update(kw)
        return RouteSessionProvenanceV1(**vals)

    def session(self, **kw):
        vals = {
            "hmac_key": ROUTE_KEY,
            "session_controller_id": "ctrl_alpha",
            "collection_session_reference": "ref_001",
            "opened_source_timestamp_us": 1_000_000,
            "ingest_timestamp_us": 1_000_100,
            "provenance": self.prov(),
        }
        vals.update(kw)
        return create_collection_session(**vals)

    def test_deterministic_identity(self):
        first = self.session()
        second = self.session()
        self.assertEqual(first.collection_session_id, second.collection_session_id)
        self.assertRegex(first.collection_session_id, r"^csn_v1_[0-9a-f]{64}$")

    def test_every_identity_input_changes_session_id(self):
        baseline = self.session()
        cases = {
            "session_controller_id": {"session_controller_id": "ctrl_beta"},
            "collection_session_reference": {"collection_session_reference": "ref_002"},
        }
        for name, overrides in cases.items():
            with self.subTest(name=name):
                changed = self.session(**overrides)
                self.assertNotEqual(baseline.collection_session_id, changed.collection_session_id)

    def test_nonidentity_fields_do_not_change_session_id(self):
        baseline = self.session()
        cases = {
            "opened_source_timestamp_us": {"opened_source_timestamp_us": 2_000_000},
            "ingest_timestamp_us": {"ingest_timestamp_us": 9_000_000},
            "provenance": {"provenance": self.prov(controller_name="other_ctrl")},
        }
        for name, overrides in cases.items():
            with self.subTest(name=name):
                changed = self.session(**overrides)
                self.assertEqual(baseline.collection_session_id, changed.collection_session_id)

    def test_different_hmac_key_changes_local_identity(self):
        baseline = self.session()
        changed = self.session(hmac_key=b"other-route-contract-test-key")
        self.assertNotEqual(baseline.collection_session_id, changed.collection_session_id)

    def test_valid_session_fields_and_immutability(self):
        s = self.session()
        self.assertIsInstance(s, CollectionSessionV1)
        self.assertEqual(s.schema_version, "1.0")
        self.assertEqual(s.record_kind, "collection_session")
        self.assertEqual(s.session_controller_id, "ctrl_alpha")
        self.assertEqual(s.collection_session_reference, "ref_001")
        self.assertEqual(s.opened_source_timestamp_us, 1_000_000)
        self.assertEqual(s.ingest_timestamp_us, 1_000_100)
        self.assertEqual(s.time_basis, "source_timestamp_us")
        self.assertEqual(s.boundary_policy, "explicit_half_open_v1")
        with self.assertRaises(FrozenInstanceError):
            s.session_controller_id = "changed"

    def test_rejects_wrong_schema_version(self):
        with self.assertRaises(ValueError):
            CollectionSessionV1(
                schema_version="2.0",
                record_kind="collection_session",
                collection_session_id="csn_v1_" + "a" * 64,
                session_controller_id="ctrl",
                collection_session_reference="ref",
                opened_source_timestamp_us=1_000_000,
                time_basis="source_timestamp_us",
                boundary_policy="explicit_half_open_v1",
                ingest_timestamp_us=1_000_100,
                provenance=self.prov(),
            )

    def test_rejects_wrong_record_kind(self):
        with self.assertRaises(ValueError):
            CollectionSessionV1(
                schema_version="1.0",
                record_kind="wrong_kind",
                collection_session_id="csn_v1_" + "a" * 64,
                session_controller_id="ctrl",
                collection_session_reference="ref",
                opened_source_timestamp_us=1_000_000,
                time_basis="source_timestamp_us",
                boundary_policy="explicit_half_open_v1",
                ingest_timestamp_us=1_000_100,
                provenance=self.prov(),
            )

    def test_rejects_invalid_timestamps(self):
        for field in ("opened_source_timestamp_us", "ingest_timestamp_us"):
            for value in (True, 1.5, -1):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        self.session(**{field: value})

    def test_session_has_no_end_us_field(self):
        s = self.session()
        self.assertTrue(hasattr(s, "opened_source_timestamp_us"))
        self.assertFalse(hasattr(s, "session_end_us"))


class CollectionSourceMembershipV1Tests(unittest.TestCase):
    @staticmethod
    def prov(**kw):
        vals = {
            "controller_name": "test_controller",
            "controller_version": "1.0.0",
            "operation_mode": "session_control",
        }
        vals.update(kw)
        return RouteSessionProvenanceV1(**vals)

    @staticmethod
    def default_session():
        return create_collection_session(
            hmac_key=ROUTE_KEY,
            session_controller_id="ctrl_alpha",
            collection_session_reference="ref_001",
            opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100,
            provenance=RouteSessionProvenanceV1(
                controller_name="test_controller",
                controller_version="1.0.0",
                operation_mode="session_control",
            ),
        )

    def membership(self, **kw):
        vals = {
            "hmac_key": ROUTE_KEY,
            "collection_session": self.default_session(),
            "source_type": "synthetic.gps",
            "sensor_id": "sensor_alpha",
            "source_instance_reference": "inst_001",
            "joined_source_timestamp_us": 1_000_000,
            "ingest_timestamp_us": 1_000_100,
            "provenance": self.prov(),
        }
        vals.update(kw)
        return create_source_membership(**vals)

    def test_deterministic_identity(self):
        first = self.membership()
        second = self.membership()
        self.assertEqual(first.membership_id, second.membership_id)
        self.assertRegex(first.membership_id, r"^csm_v1_[0-9a-f]{64}$")

    def test_every_identity_input_changes_membership_id(self):
        baseline = self.membership()
        alt_session = create_collection_session(
            hmac_key=ROUTE_KEY,
            session_controller_id="ctrl_beta",
            collection_session_reference="ref_002",
            opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100,
            provenance=self.prov(),
        )
        cases = {
            "session": {"collection_session": alt_session},
            "source_type": {"source_type": "synthetic.alternate"},
            "sensor_id": {"sensor_id": "sensor_beta"},
            "instance_ref": {"source_instance_reference": "inst_002"},
        }
        for name, overrides in cases.items():
            with self.subTest(name=name):
                changed = self.membership(**overrides)
                self.assertNotEqual(baseline.membership_id, changed.membership_id)

    def test_nonidentity_fields_do_not_change_membership_id(self):
        baseline = self.membership()
        cases = {
            "joined_source_timestamp_us": {"joined_source_timestamp_us": 2_000_000},
            "ingest_timestamp_us": {"ingest_timestamp_us": 9_000_000},
            "provenance": {"provenance": self.prov(controller_name="other")},
        }
        for name, overrides in cases.items():
            with self.subTest(name=name):
                changed = self.membership(**overrides)
                self.assertEqual(baseline.membership_id, changed.membership_id)

    def test_different_hmac_key_changes_local_identity(self):
        baseline = self.membership()
        changed = self.membership(hmac_key=b"other-route-contract-test-key")
        self.assertNotEqual(baseline.membership_id, changed.membership_id)

    def test_valid_fields_and_immutability(self):
        m = self.membership()
        self.assertIsInstance(m, CollectionSourceMembershipV1)
        self.assertEqual(m.schema_version, "1.0")
        self.assertEqual(m.record_kind, "collection_source_membership")
        self.assertEqual(m.joined_source_timestamp_us, 1_000_000)
        with self.assertRaises(FrozenInstanceError):
            m.sensor_id = "changed"

    def test_membership_has_no_end_us_time_basis_boundary_policy(self):
        m = self.membership()
        self.assertFalse(hasattr(m, "membership_end_us"))
        self.assertFalse(hasattr(m, "time_basis"))
        self.assertFalse(hasattr(m, "boundary_policy"))

    def test_rejects_invalid_source_type(self):
        with self.assertRaises(ValueError):
            self.membership(source_type="Invalid.Type")

    def test_rejects_invalid_timestamps(self):
        for field in ("joined_source_timestamp_us", "ingest_timestamp_us"):
            for value in (True, 1.5, -1):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        self.membership(**{field: value})


class MembershipCloseAndSessionCloseTests(unittest.TestCase):
    @staticmethod
    def prov(**kw):
        vals = {
            "controller_name": "test_controller",
            "controller_version": "1.0.0",
            "operation_mode": "session_control",
        }
        vals.update(kw)
        return RouteSessionProvenanceV1(**vals)

    def test_membership_close_deterministic_identity(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        first = create_membership_close(
            hmac_key=ROUTE_KEY, membership=membership,
            left_source_timestamp_us=3_000_000, close_reason="normal",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        second = create_membership_close(
            hmac_key=ROUTE_KEY, membership=membership,
            left_source_timestamp_us=3_000_000, close_reason="normal",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        self.assertEqual(first.membership_close_id, second.membership_close_id)
        self.assertRegex(first.membership_close_id, r"^cmc_v1_[0-9a-f]{64}$")
        self.assertEqual(first.membership_id, membership.membership_id)

    def test_membership_close_same_membership_different_timestamp_conflict(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        first = create_membership_close(
            hmac_key=ROUTE_KEY, membership=membership,
            left_source_timestamp_us=3_000_000, close_reason="normal",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        second = create_membership_close(
            hmac_key=ROUTE_KEY, membership=membership,
            left_source_timestamp_us=4_000_000, close_reason="normal",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        self.assertEqual(first.membership_close_id, second.membership_close_id)
        self.assertEqual(
            compare_membership_close_source_facts(first, second),
            "identity_conflict",
        )

    def test_membership_close_reason_validation(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            create_membership_close(
                hmac_key=ROUTE_KEY, membership=membership,
                left_source_timestamp_us=3_000_000, close_reason="invalid_reason",
                ingest_timestamp_us=1_000_200, provenance=self.prov(),
            )

    def test_membership_close_all_reasons_accepted(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        for reason in ("normal", "source_restart", "source_failure", "session_closed", "aborted"):
            with self.subTest(reason=reason):
                close = create_membership_close(
                    hmac_key=ROUTE_KEY, membership=membership,
                    left_source_timestamp_us=3_000_000, close_reason=reason,
                    ingest_timestamp_us=1_000_200, provenance=self.prov(),
                )
                self.assertEqual(close.close_reason, reason)

    def test_session_close_deterministic_identity(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        first = create_session_close(
            hmac_key=ROUTE_KEY, collection_session=session,
            closed_source_timestamp_us=5_000_000, close_reason="completed",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        second = create_session_close(
            hmac_key=ROUTE_KEY, collection_session=session,
            closed_source_timestamp_us=5_000_000, close_reason="completed",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        self.assertEqual(first.session_close_id, second.session_close_id)
        self.assertRegex(first.session_close_id, r"^csc_v1_[0-9a-f]{64}$")
        self.assertEqual(first.collection_session_id, session.collection_session_id)

    def test_session_close_reason_validation(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            create_session_close(
                hmac_key=ROUTE_KEY, collection_session=session,
                closed_source_timestamp_us=5_000_000, close_reason="invalid",
                ingest_timestamp_us=1_000_200, provenance=self.prov(),
            )

    def test_session_close_all_reasons_accepted(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        for reason in ("completed", "operator_closed", "aborted", "clock_invalid"):
            with self.subTest(reason=reason):
                close = create_session_close(
                    hmac_key=ROUTE_KEY, collection_session=session,
                    closed_source_timestamp_us=5_000_000, close_reason=reason,
                    ingest_timestamp_us=1_000_200, provenance=self.prov(),
                )
                self.assertEqual(close.close_reason, reason)

    def test_session_close_same_session_different_timestamp_conflict(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        first = create_session_close(
            hmac_key=ROUTE_KEY, collection_session=session,
            closed_source_timestamp_us=5_000_000, close_reason="completed",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        second = create_session_close(
            hmac_key=ROUTE_KEY, collection_session=session,
            closed_source_timestamp_us=6_000_000, close_reason="completed",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        self.assertEqual(first.session_close_id, second.session_close_id)
        self.assertEqual(compare_session_close_source_facts(first, second), "identity_conflict")

    def test_membership_close_is_frozen(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        close = create_membership_close(
            hmac_key=ROUTE_KEY, membership=membership,
            left_source_timestamp_us=3_000_000, close_reason="normal",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        with self.assertRaises(FrozenInstanceError):
            close.left_source_timestamp_us = 9_999_999

    def test_session_close_is_frozen(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        close = create_session_close(
            hmac_key=ROUTE_KEY, collection_session=session,
            closed_source_timestamp_us=5_000_000, close_reason="completed",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        with self.assertRaises(FrozenInstanceError):
            close.collection_session_id = "changed"


class RouteV1Tests(unittest.TestCase):
    SESSION_ID = "csn_v1_" + "a" * 64

    @staticmethod
    def prov(**kw):
        vals = {
            "controller_name": "test_controller",
            "controller_version": "1.0.0",
            "operation_mode": "route_snapshot",
        }
        vals.update(kw)
        return RouteSessionProvenanceV1(**vals)

    @staticmethod
    def ofix(timestamp_us=1_000_000, session_id=None, ref="r1", **kw):
        vals = {
            "hmac_key": OBSERVATION_KEY,
            "collection_session_id": session_id or "csn_v1_" + "a" * 64,
            "source_type": "synthetic.gps",
            "sensor_id": "sensor_alpha",
            "operator_fix_timestamp_us": timestamp_us,
            "ingest_timestamp_us": 1_000_100,
            "source_record_reference": ref,
            "provenance": _obs_prov(),
            "operator_latitude": 33.0,
            "operator_longitude": -112.0,
            "operator_location_accuracy_m": 5.0,
        }
        vals.update(kw)
        return create_operator_fix(**vals)

    def route(self, **kw):
        vals = {
            "hmac_key": ROUTE_KEY,
            "collection_session_id": self.SESSION_ID,
            "route_method": "operator_fix_gap_partition",
            "route_version": "1.0",
            "max_internal_gap_us": 500_000,
            "operator_fixes": [
                self.ofix(timestamp_us=1_000_000, ref="ra"),
                self.ofix(timestamp_us=1_200_000, ref="rb"),
            ],
            "provenance": self.prov(),
            "created_ingest_timestamp_us": 2_000_000,
        }
        vals.update(kw)
        return create_route(**vals)

    def test_deterministic_identity(self):
        first = self.route()
        second = self.route()
        self.assertEqual(first.route_id, second.route_id)
        self.assertRegex(first.route_id, r"^rte_v1_[0-9a-f]{64}$")

    def test_every_identity_input_changes_route_id(self):
        baseline = self.route()
        other_session = "csn_v1_" + "b" * 64
        other_fixes = [self.ofix(timestamp_us=1_000_000, ref="rx", session_id=other_session)]
        cases = {
            "session_id": {
                "collection_session_id": other_session,
                "operator_fixes": other_fixes,
            },
            "method": {"route_method": "other_method"},
            "version": {"route_version": "2.0"},
            "gap": {"max_internal_gap_us": 999_999},
            "fix_ids": {"operator_fixes": [self.ofix(timestamp_us=1_000_000, ref="rx")]},
        }
        for name, overrides in cases.items():
            with self.subTest(name=name):
                changed = self.route(**overrides)
                self.assertNotEqual(baseline.route_id, changed.route_id)

    def test_nonidentity_fields_do_not_change_route_id(self):
        baseline = self.route()
        changed = self.route(
            provenance=self.prov(controller_name="other_controller"),
        )
        self.assertEqual(baseline.route_id, changed.route_id)

    def test_different_hmac_key_changes_route_id(self):
        baseline = self.route()
        changed = self.route(hmac_key=b"other-route-contract-test-key")
        self.assertNotEqual(baseline.route_id, changed.route_id)

    def test_timestamp_ordering_canonical(self):
        fix_a = self.ofix(timestamp_us=1_500_000, ref="ra")
        fix_b = self.ofix(timestamp_us=1_000_000, ref="rb")
        r1 = self.route(operator_fixes=[fix_a, fix_b])
        r2 = self.route(operator_fixes=[fix_b, fix_a])
        self.assertEqual(r1.route_id, r2.route_id)
        self.assertEqual(r1.started_source_timestamp_us, 1_000_000)
        self.assertEqual(r1.ended_source_timestamp_us, 1_500_000)
        self.assertEqual(r1.point_count, 2)

    def test_same_timestamp_ordered_by_id(self):
        fix_a = self.ofix(timestamp_us=1_000_000, ref="ra")
        fix_b = self.ofix(timestamp_us=1_000_000, ref="rb")
        ra_id = fix_a.operator_fix_id
        rb_id = fix_b.operator_fix_id
        r = self.route(operator_fixes=[fix_b, fix_a])
        if ra_id < rb_id:
            self.assertEqual(list(r.ordered_operator_fix_ids), [ra_id, rb_id])
        else:
            self.assertEqual(list(r.ordered_operator_fix_ids), [rb_id, ra_id])

    def test_started_ended_timestamps_derived(self):
        fixes = [
            self.ofix(timestamp_us=1_100_000, ref="rc"),
            self.ofix(timestamp_us=1_000_000, ref="ra"),
            self.ofix(timestamp_us=1_200_000, ref="rb"),
        ]
        r = self.route(operator_fixes=fixes)
        self.assertEqual(r.started_source_timestamp_us, 1_000_000)
        self.assertEqual(r.ended_source_timestamp_us, 1_200_000)
        self.assertEqual(r.point_count, 3)

    def test_rejects_empty_fixes(self):
        with self.assertRaises(ValueError):
            self.route(operator_fixes=[])

    def test_rejects_duplicate_fix_ids(self):
        with self.assertRaises(ValueError):
            self.route(operator_fixes=[
                self.ofix(timestamp_us=1_000_000, ref="ra"),
                self.ofix(timestamp_us=2_000_000, ref="ra"),
            ])

    def test_rejects_cross_session_fixes(self):
        wrong_fix = create_operator_fix(
            hmac_key=OBSERVATION_KEY,
            collection_session_id="csn_v1_" + "z" * 64,
            source_type="synthetic.gps",
            sensor_id="sensor_a",
            operator_fix_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100,
            source_record_reference="fix_wrong",
            provenance=_obs_prov(),
            operator_latitude=33.0,
            operator_longitude=-112.0,
        )
        with self.assertRaises(ValueError):
            self.route(operator_fixes=[wrong_fix, self.ofix(timestamp_us=1_000_000, ref="ra")])

    def test_rejects_excessive_gap(self):
        fixes = [
            self.ofix(timestamp_us=1_000_000, ref="ra"),
            self.ofix(timestamp_us=2_000_000, ref="rb"),
        ]
        with self.assertRaises(ValueError):
            self.route(operator_fixes=fixes, max_internal_gap_us=500_000)

    def test_allows_gap_equal_to_max(self):
        fixes = [
            self.ofix(timestamp_us=1_000_000, ref="ra"),
            self.ofix(timestamp_us=1_500_000, ref="rb"),
        ]
        r = self.route(operator_fixes=fixes, max_internal_gap_us=500_000)
        self.assertEqual(r.point_count, 2)

    def test_route_is_frozen(self):
        r = self.route()
        with self.assertRaises(FrozenInstanceError):
            r.route_method = "changed"

    def test_rejects_negative_gap(self):
        with self.assertRaises(ValueError):
            self.route(max_internal_gap_us=-1)

    def test_default_method_and_version(self):
        r = self.route()
        self.assertEqual(r.route_method, "operator_fix_gap_partition")
        self.assertEqual(r.route_version, "1.0")


class AnalysisSessionV1Tests(unittest.TestCase):
    @staticmethod
    def prov(**kw):
        vals = {
            "controller_name": "test_controller",
            "controller_version": "1.0.0",
            "operation_mode": "analysis",
        }
        vals.update(kw)
        return RouteSessionProvenanceV1(**vals)

    def analysis(self, **kw):
        vals = {
            "hmac_key": ROUTE_KEY,
            "analysis_type": "repeated_observation_review",
            "analysis_version": "1.0",
            "collection_session_ids": ["csn_v1_" + "a" * 64, "csn_v1_" + "b" * 64],
            "route_ids": ["rte_v1_" + "c" * 64, "rte_v1_" + "d" * 64],
            "input_manifest_digest": "e" * 64,
            "provenance": self.prov(),
            "created_ingest_timestamp_us": 2_000_000,
        }
        vals.update(kw)
        return create_analysis_session(**vals)

    def test_deterministic_identity(self):
        first = self.analysis()
        second = self.analysis()
        self.assertEqual(first.analysis_session_id, second.analysis_session_id)
        self.assertRegex(first.analysis_session_id, r"^asn_v1_[0-9a-f]{64}$")

    def test_every_identity_input_changes_analysis_id(self):
        baseline = self.analysis()
        cases = {
            "type": {"analysis_type": "location_pattern_review"},
            "version": {"analysis_version": "2.0"},
            "digest": {"input_manifest_digest": "f" * 64},
        }
        for name, overrides in cases.items():
            with self.subTest(name=name):
                changed = self.analysis(**overrides)
                self.assertNotEqual(baseline.analysis_session_id, changed.analysis_session_id)

    def test_identity_independent_of_input_order(self):
        sa = "csn_v1_" + "a" * 64
        sb = "csn_v1_" + "b" * 64
        ra = "rte_v1_" + "c" * 64
        rb = "rte_v1_" + "d" * 64
        forward = self.analysis(collection_session_ids=[sa, sb], route_ids=[ra, rb])
        reverse = self.analysis(collection_session_ids=[sb, sa], route_ids=[rb, ra])
        self.assertEqual(forward.analysis_session_id, reverse.analysis_session_id)
        self.assertEqual(forward.ordered_collection_session_ids, (sa, sb))
        self.assertEqual(forward.ordered_route_ids, (ra, rb))

    def test_empty_collection_session_ids_rejected(self):
        with self.assertRaises(ValueError):
            self.analysis(collection_session_ids=[])

    def test_empty_route_ids_allowed(self):
        a = self.analysis(route_ids=[])
        self.assertEqual(a.ordered_route_ids, ())

    def test_duplicate_session_ids_rejected(self):
        sid = "csn_v1_" + "a" * 64
        with self.assertRaises(ValueError):
            self.analysis(collection_session_ids=[sid, sid])

    def test_duplicate_route_ids_rejected(self):
        rid = "rte_v1_" + "a" * 64
        with self.assertRaises(ValueError):
            self.analysis(route_ids=[rid, rid])

    def test_invalid_digest_rejected(self):
        with self.assertRaises(ValueError):
            self.analysis(input_manifest_digest="xyz")

    def test_nonidentity_fields_do_not_change_analysis_id(self):
        baseline = self.analysis()
        changed = self.analysis(
            provenance=self.prov(controller_name="other_controller"),
        )
        self.assertEqual(baseline.analysis_session_id, changed.analysis_session_id)

    def test_different_hmac_key_changes_analysis_id(self):
        baseline = self.analysis()
        changed = self.analysis(hmac_key=b"other-key")
        self.assertNotEqual(baseline.analysis_session_id, changed.analysis_session_id)

    def test_analysis_session_is_frozen(self):
        a = self.analysis()
        with self.assertRaises(FrozenInstanceError):
            a.analysis_type = "changed"

    def test_manifest_version_change_alters_identity(self):
        v1 = self.analysis(analysis_version="1.0")
        v2 = self.analysis(analysis_version="2.0")
        self.assertNotEqual(v1.analysis_session_id, v2.analysis_session_id)


class ComparisonTests(unittest.TestCase):
    @staticmethod
    def prov(**kw):
        vals = {
            "controller_name": "test_controller",
            "controller_version": "1.0.0",
            "operation_mode": "session_control",
        }
        vals.update(kw)
        return RouteSessionProvenanceV1(**vals)

    def test_session_duplicate_ignores_ingest_and_provenance(self):
        existing = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        incoming = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=9_000_000, provenance=self.prov(controller_name="other"),
        )
        self.assertEqual(existing.collection_session_id, incoming.collection_session_id)
        self.assertEqual(
            compare_collection_session_source_facts(existing, incoming),
            "duplicate",
        )

    def test_session_changed_boundary_is_conflict(self):
        existing = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        incoming = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=2_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        self.assertEqual(existing.collection_session_id, incoming.collection_session_id)
        self.assertEqual(
            compare_collection_session_source_facts(existing, incoming),
            "identity_conflict",
        )

    def test_membership_duplicate_ignores_ingest_and_provenance(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        existing = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        incoming = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=9_000_000, provenance=self.prov(controller_name="other"),
        )
        self.assertEqual(existing.membership_id, incoming.membership_id)
        self.assertEqual(
            compare_source_membership_source_facts(existing, incoming),
            "duplicate",
        )

    def test_membership_changed_join_is_conflict(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        existing = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        incoming = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=2_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        self.assertEqual(existing.membership_id, incoming.membership_id)
        self.assertEqual(
            compare_source_membership_source_facts(existing, incoming),
            "identity_conflict",
        )

    def test_membership_close_duplicate_ignores_ingest_and_provenance(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        existing = create_membership_close(
            hmac_key=ROUTE_KEY, membership=membership,
            left_source_timestamp_us=3_000_000, close_reason="normal",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        incoming = create_membership_close(
            hmac_key=ROUTE_KEY, membership=membership,
            left_source_timestamp_us=3_000_000, close_reason="normal",
            ingest_timestamp_us=9_000_000, provenance=self.prov(controller_name="other"),
        )
        self.assertEqual(existing.membership_close_id, incoming.membership_close_id)
        self.assertEqual(compare_membership_close_source_facts(existing, incoming), "duplicate")

    def test_membership_close_changed_reason_is_conflict(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        existing = create_membership_close(
            hmac_key=ROUTE_KEY, membership=membership,
            left_source_timestamp_us=3_000_000, close_reason="normal",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        incoming = create_membership_close(
            hmac_key=ROUTE_KEY, membership=membership,
            left_source_timestamp_us=3_000_000, close_reason="source_failure",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        self.assertEqual(existing.membership_close_id, incoming.membership_close_id)
        self.assertEqual(compare_membership_close_source_facts(existing, incoming), "identity_conflict")

    def test_session_close_duplicate_ignores_ingest_and_provenance(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        existing = create_session_close(
            hmac_key=ROUTE_KEY, collection_session=session,
            closed_source_timestamp_us=5_000_000, close_reason="completed",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        incoming = create_session_close(
            hmac_key=ROUTE_KEY, collection_session=session,
            closed_source_timestamp_us=5_000_000, close_reason="completed",
            ingest_timestamp_us=9_000_000, provenance=self.prov(controller_name="other"),
        )
        self.assertEqual(existing.session_close_id, incoming.session_close_id)
        self.assertEqual(compare_session_close_source_facts(existing, incoming), "duplicate")

    def test_route_duplicate_ignores_provenance_and_ingest(self):
        fixes = [
            _fix(collection_session_id="csn_v1_" + "a" * 64,
                 operator_fix_timestamp_us=1_000_000,
                 source_record_reference="fix_route_a"),
            _fix(collection_session_id="csn_v1_" + "a" * 64,
                 operator_fix_timestamp_us=1_200_000,
                 source_record_reference="fix_route_b"),
        ]
        existing = create_route(
            hmac_key=ROUTE_KEY, collection_session_id="csn_v1_" + "a" * 64,
            operator_fixes=fixes, provenance=self.prov(operation_mode="route_snapshot"),
            max_internal_gap_us=500_000, created_ingest_timestamp_us=2_000_000,
        )
        incoming = create_route(
            hmac_key=ROUTE_KEY, collection_session_id="csn_v1_" + "a" * 64,
            operator_fixes=fixes, provenance=self.prov(operation_mode="route_snapshot", controller_name="other"),
            max_internal_gap_us=500_000, created_ingest_timestamp_us=9_000_000,
        )
        self.assertEqual(existing.route_id, incoming.route_id)
        self.assertEqual(compare_route_source_facts(existing, incoming), "duplicate")

    def test_route_changed_started_timestamp_is_conflict(self):
        def make(started=1_000_000):
            return RouteV1(
                schema_version="1.0",
                record_kind="route",
                route_id="rte_v1_" + "a" * 64,
                collection_session_id="csn_v1_" + "a" * 64,
                route_method="operator_fix_gap_partition",
                route_version="1.0",
                max_internal_gap_us=500_000,
                ordered_operator_fix_ids=("fix_a", "fix_b"),
                started_source_timestamp_us=started,
                ended_source_timestamp_us=2_000_000,
                point_count=2,
                created_ingest_timestamp_us=2_000_000,
                provenance=self.prov(operation_mode="route_snapshot"),
            )
        existing = make()
        incoming = make(started=1_500_000)
        self.assertEqual(existing.route_id, incoming.route_id)
        self.assertEqual(
            compare_route_source_facts(existing, incoming),
            "identity_conflict",
        )

    def test_route_changed_ended_timestamp_is_conflict(self):
        def make(ended=2_000_000):
            return RouteV1(
                schema_version="1.0",
                record_kind="route",
                route_id="rte_v1_" + "a" * 64,
                collection_session_id="csn_v1_" + "a" * 64,
                route_method="operator_fix_gap_partition",
                route_version="1.0",
                max_internal_gap_us=500_000,
                ordered_operator_fix_ids=("fix_a", "fix_b"),
                started_source_timestamp_us=1_000_000,
                ended_source_timestamp_us=ended,
                point_count=2,
                created_ingest_timestamp_us=2_000_000,
                provenance=self.prov(operation_mode="route_snapshot"),
            )
        existing = make()
        incoming = make(ended=2_500_000)
        self.assertEqual(existing.route_id, incoming.route_id)
        self.assertEqual(
            compare_route_source_facts(existing, incoming),
            "identity_conflict",
        )

    def test_route_changed_point_count_is_conflict(self):
        # Corruption/tampering detection: mutate only point_count post-construction
        existing = RouteV1(
            schema_version="1.0",
            record_kind="route",
            route_id="rte_v1_" + "a" * 64,
            collection_session_id="csn_v1_" + "a" * 64,
            route_method="operator_fix_gap_partition",
            route_version="1.0",
            max_internal_gap_us=500_000,
            ordered_operator_fix_ids=("fix_a", "fix_b"),
            started_source_timestamp_us=1_000_000,
            ended_source_timestamp_us=2_000_000,
            point_count=2,
            created_ingest_timestamp_us=2_000_000,
            provenance=self.prov(operation_mode="route_snapshot"),
        )
        incoming = RouteV1(
            schema_version="1.0",
            record_kind="route",
            route_id="rte_v1_" + "a" * 64,
            collection_session_id="csn_v1_" + "a" * 64,
            route_method="operator_fix_gap_partition",
            route_version="1.0",
            max_internal_gap_us=500_000,
            ordered_operator_fix_ids=("fix_a", "fix_b"),
            started_source_timestamp_us=1_000_000,
            ended_source_timestamp_us=2_000_000,
            point_count=2,
            created_ingest_timestamp_us=2_000_000,
            provenance=self.prov(operation_mode="route_snapshot"),
        )
        object.__setattr__(incoming, "point_count", 99)
        self.assertEqual(existing.route_id, incoming.route_id)
        self.assertEqual(
            compare_route_source_facts(existing, incoming),
            "identity_conflict",
        )

    def test_analysis_duplicate_ignores_provenance_and_ingest(self):
        existing = create_analysis_session(
            hmac_key=ROUTE_KEY, analysis_type="review", analysis_version="1.0",
            collection_session_ids=["csn_v1_" + "a" * 64],
            route_ids=["rte_v1_" + "b" * 64],
            input_manifest_digest="c" * 64,
            provenance=self.prov(operation_mode="analysis"),
            created_ingest_timestamp_us=2_000_000,
        )
        incoming = create_analysis_session(
            hmac_key=ROUTE_KEY, analysis_type="review", analysis_version="1.0",
            collection_session_ids=["csn_v1_" + "a" * 64],
            route_ids=["rte_v1_" + "b" * 64],
            input_manifest_digest="c" * 64,
            provenance=self.prov(operation_mode="analysis", controller_name="other"),
            created_ingest_timestamp_us=9_000_000,
        )
        self.assertEqual(existing.analysis_session_id, incoming.analysis_session_id)
        self.assertEqual(compare_analysis_session_source_facts(existing, incoming), "duplicate")

    def test_different_ids_return_identity_conflict(self):
        existing = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl_a",
            collection_session_reference="ref_a", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        incoming = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl_b",
            collection_session_reference="ref_b", opened_source_timestamp_us=2_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        self.assertEqual(
            compare_collection_session_source_facts(existing, incoming),
            "identity_conflict",
        )


class BoundaryValidationTests(unittest.TestCase):
    @staticmethod
    def prov(**kw):
        vals = {
            "controller_name": "test_controller",
            "controller_version": "1.0.0",
            "operation_mode": "session_control",
        }
        vals.update(kw)
        return RouteSessionProvenanceV1(**vals)

    def test_session_open_before_close_valid(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        close = create_session_close(
            hmac_key=ROUTE_KEY, collection_session=session,
            closed_source_timestamp_us=5_000_000, close_reason="completed",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        validate_collection_session_boundaries(session, session_close=close)

    def test_session_open_equals_close_valid(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        close = create_session_close(
            hmac_key=ROUTE_KEY, collection_session=session,
            closed_source_timestamp_us=1_000_000, close_reason="completed",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        validate_collection_session_boundaries(session, session_close=close)

    def test_session_open_after_close_rejected(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=5_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        close = create_session_close(
            hmac_key=ROUTE_KEY, collection_session=session,
            closed_source_timestamp_us=1_000_000, close_reason="completed",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            validate_collection_session_boundaries(session, session_close=close)

    def test_membership_join_before_left_valid(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        close = create_membership_close(
            hmac_key=ROUTE_KEY, membership=membership,
            left_source_timestamp_us=3_000_000, close_reason="normal",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        validate_source_membership_boundaries(membership, membership_close=close)

    def test_membership_join_after_left_rejected(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=5_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        close = create_membership_close(
            hmac_key=ROUTE_KEY, membership=membership,
            left_source_timestamp_us=3_000_000, close_reason="normal",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            validate_source_membership_boundaries(membership, membership_close=close)

    def test_membership_wrong_parent_session_rejected(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        other_session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl_other",
            collection_session_reference="ref_other", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=other_session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            validate_source_membership_boundaries(
                membership,
                session_collection_session_id=session.collection_session_id,
            )


class SourceRecordAdmissionTests(unittest.TestCase):
    @staticmethod
    def prov(**kw):
        vals = {
            "controller_name": "test_controller",
            "controller_version": "1.0.0",
            "operation_mode": "session_control",
        }
        vals.update(kw)
        return RouteSessionProvenanceV1(**vals)

    def test_exact_half_open_admission(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        validate_source_record_admission(session, membership, 1_000_000)
        validate_source_record_admission(session, membership, 2_500_000)

    def test_at_close_timestamp_rejected(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        close = create_membership_close(
            hmac_key=ROUTE_KEY, membership=membership,
            left_source_timestamp_us=3_000_000, close_reason="normal",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            validate_source_record_admission(session, membership, 3_000_000, membership_close=close)

    def test_before_open_rejected(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            validate_source_record_admission(session, membership, 999_999)

    def test_before_join_rejected(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=2_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            validate_source_record_admission(session, membership, 1_500_000)

    def test_late_in_bound_accepted(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        validate_source_record_admission(session, membership, 3_500_000)

    def test_rejects_bool_source_timestamp(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            validate_source_record_admission(session, membership, True)

    def test_rejects_float_source_timestamp(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            validate_source_record_admission(session, membership, 1.5)

    def test_rejects_negative_source_timestamp(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            validate_source_record_admission(session, membership, -1)

    def test_wrong_parent_membership_rejected(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        other_session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl_other",
            collection_session_reference="ref_other", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=other_session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            validate_source_record_admission(session, membership, 1_500_000)

    def test_wrong_parent_session_close_rejected(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        other_session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl_other",
            collection_session_reference="ref_other", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        wrong_close = create_session_close(
            hmac_key=ROUTE_KEY, collection_session=other_session,
            closed_source_timestamp_us=5_000_000, close_reason="completed",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            validate_source_record_admission(session, membership, 1_500_000, session_close=wrong_close)

    def test_wrong_membership_close_rejected(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        other_membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.wifi", sensor_id="sensor_b",
            source_instance_reference="inst_002", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        wrong_close = create_membership_close(
            hmac_key=ROUTE_KEY, membership=other_membership,
            left_source_timestamp_us=3_000_000, close_reason="normal",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            validate_source_record_admission(
                session, membership, 1_500_000, membership_close=wrong_close,
            )

    def test_membership_close_exceeds_session_close_rejected(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        session_close = create_session_close(
            hmac_key=ROUTE_KEY, collection_session=session,
            closed_source_timestamp_us=4_000_000, close_reason="completed",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        membership_close = create_membership_close(
            hmac_key=ROUTE_KEY, membership=membership,
            left_source_timestamp_us=5_000_000, close_reason="normal",
            ingest_timestamp_us=1_000_200, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            validate_source_record_admission(
                session, membership, 1_500_000,
                session_close=session_close, membership_close=membership_close,
            )


class MembershipOverlapTests(unittest.TestCase):
    @staticmethod
    def prov(**kw):
        vals = {
            "controller_name": "test_controller",
            "controller_version": "1.0.0",
            "operation_mode": "session_control",
        }
        vals.update(kw)
        return RouteSessionProvenanceV1(**vals)

    def session(self, **kw):
        vals = {
            "hmac_key": ROUTE_KEY,
            "session_controller_id": "ctrl",
            "collection_session_reference": "ref",
            "opened_source_timestamp_us": 1_000_000,
            "ingest_timestamp_us": 1_000_100,
            "provenance": self.prov(),
        }
        vals.update(kw)
        return create_collection_session(**vals)

    def membership(self, session, **kw):
        vals = {
            "hmac_key": ROUTE_KEY,
            "collection_session": session,
            "source_type": "synthetic.gps",
            "sensor_id": "sensor_a",
            "source_instance_reference": "inst_001",
            "joined_source_timestamp_us": 1_000_000,
            "ingest_timestamp_us": 1_000_100,
            "provenance": self.prov(),
        }
        vals.update(kw)
        return create_source_membership(**vals)

    def close(self, membership, **kw):
        vals = {
            "hmac_key": ROUTE_KEY,
            "membership": membership,
            "left_source_timestamp_us": 3_000_000,
            "close_reason": "normal",
            "ingest_timestamp_us": 1_000_200,
            "provenance": self.prov(),
        }
        vals.update(kw)
        return create_membership_close(**vals)

    def test_non_overlapping_adjacent_memberships(self):
        session = self.session()
        a = self.membership(session, sensor_id="sensor_a",
                            source_instance_reference="inst_001",
                            joined_source_timestamp_us=1_000_000)
        a_close = self.close(a, left_source_timestamp_us=2_000_000)
        b = self.membership(session, sensor_id="sensor_a",
                            source_instance_reference="inst_002",
                            joined_source_timestamp_us=2_000_000)
        validate_no_membership_overlap([(a, a_close), (b, None)])

    def test_overlapping_memberships_rejected(self):
        session = self.session()
        a = self.membership(session, sensor_id="sensor_a",
                            source_instance_reference="inst_001",
                            joined_source_timestamp_us=1_000_000)
        b = self.membership(session, sensor_id="sensor_a",
                            source_instance_reference="inst_002",
                            joined_source_timestamp_us=2_000_000)
        with self.assertRaises(ValueError):
            validate_no_membership_overlap([(a, None), (b, None)])

    def test_open_memberships_overlap_rejected(self):
        session = self.session()
        a = self.membership(session, sensor_id="sensor_a",
                            source_instance_reference="inst_001",
                            joined_source_timestamp_us=1_000_000)
        b = self.membership(session, sensor_id="sensor_a",
                            source_instance_reference="inst_002",
                            joined_source_timestamp_us=2_000_000)
        b_close = self.close(b, left_source_timestamp_us=5_000_000)
        with self.assertRaises(ValueError):
            validate_no_membership_overlap([(a, None), (b, b_close)])

    def test_restart_no_overlap(self):
        session = self.session()
        a = self.membership(session, sensor_id="sensor_a",
                            source_instance_reference="inst_001",
                            joined_source_timestamp_us=1_000_000)
        a_close = self.close(a, left_source_timestamp_us=2_000_000)
        b = self.membership(session, sensor_id="sensor_a",
                            source_instance_reference="inst_001",
                            joined_source_timestamp_us=2_000_000)
        validate_no_membership_overlap([(a, a_close), (b, None)])

    def test_restart_with_gap_no_overlap(self):
        session = self.session()
        a = self.membership(session, sensor_id="sensor_a",
                            source_instance_reference="inst_001",
                            joined_source_timestamp_us=1_000_000)
        a_close = self.close(a, left_source_timestamp_us=2_000_000)
        b = self.membership(session, sensor_id="sensor_a",
                            source_instance_reference="inst_001",
                            joined_source_timestamp_us=3_000_000)
        validate_no_membership_overlap([(a, a_close), (b, None)])

    def test_different_sensor_no_overlap_check(self):
        session = self.session()
        a = self.membership(session, sensor_id="sensor_a",
                            source_instance_reference="inst_001",
                            joined_source_timestamp_us=1_000_000)
        b = self.membership(session, sensor_id="sensor_b",
                            source_instance_reference="inst_002",
                            joined_source_timestamp_us=2_000_000)
        validate_no_membership_overlap([(a, None), (b, None)])

    def test_different_session_no_overlap_check(self):
        s1 = self.session(session_controller_id="ctrl_1")
        s2 = self.session(session_controller_id="ctrl_2")
        a = self.membership(s1, sensor_id="sensor_a",
                            source_instance_reference="inst_001",
                            joined_source_timestamp_us=1_000_000)
        b = self.membership(s2, sensor_id="sensor_a",
                            source_instance_reference="inst_002",
                            joined_source_timestamp_us=2_000_000)
        validate_no_membership_overlap([(a, None), (b, None)])

    def test_membership_contained_within_another_rejected(self):
        session = self.session()
        a = self.membership(session, sensor_id="sensor_a",
                            source_instance_reference="inst_001",
                            joined_source_timestamp_us=1_000_000)
        a_close = self.close(a, left_source_timestamp_us=5_000_000)
        b = self.membership(session, sensor_id="sensor_a",
                            source_instance_reference="inst_002",
                            joined_source_timestamp_us=2_000_000)
        b_close = self.close(b, left_source_timestamp_us=4_000_000)
        with self.assertRaises(ValueError):
            validate_no_membership_overlap([(a, a_close), (b, b_close)])


class RouteFixInputValidationTests(unittest.TestCase):
    SESSION_ID = "csn_v1_" + "a" * 64

    def test_valid_fixes_accepted(self):
        fixes = [
            _fix(collection_session_id=self.SESSION_ID, operator_fix_timestamp_us=1_000_000,
                 source_record_reference="vfa"),
            _fix(collection_session_id=self.SESSION_ID, operator_fix_timestamp_us=2_000_000,
                 source_record_reference="vfb"),
        ]
        validate_route_fix_inputs(fixes, self.SESSION_ID)

    def test_empty_fixes_rejected(self):
        with self.assertRaises(ValueError):
            validate_route_fix_inputs([], self.SESSION_ID)

    def test_cross_session_fixes_rejected(self):
        fixes = [
            _fix(collection_session_id=self.SESSION_ID, source_record_reference="csa"),
            _fix(collection_session_id="csn_v1_" + "z" * 64, source_record_reference="csb"),
        ]
        with self.assertRaises(ValueError):
            validate_route_fix_inputs(fixes, self.SESSION_ID)

    def test_duplicate_fix_ids_rejected(self):
        fixes = [
            _fix(collection_session_id=self.SESSION_ID, source_record_reference="dup",
                 operator_fix_timestamp_us=1_000_000),
            _fix(collection_session_id=self.SESSION_ID, source_record_reference="dup",
                 operator_fix_timestamp_us=2_000_000),
        ]
        with self.assertRaises(ValueError):
            validate_route_fix_inputs(fixes, self.SESSION_ID)

    def test_wrong_type_rejected(self):
        with self.assertRaises(ValueError):
            validate_route_fix_inputs(["not-a-fix"], self.SESSION_ID)


class EdgeCaseTests(unittest.TestCase):
    @staticmethod
    def prov(**kw):
        vals = {
            "controller_name": "test_controller",
            "controller_version": "1.0.0",
            "operation_mode": "session_control",
        }
        vals.update(kw)
        return RouteSessionProvenanceV1(**vals)

    def test_hmac_key_must_be_non_empty_bytes(self):
        with self.assertRaises(ValueError):
            create_collection_session(
                hmac_key=None, session_controller_id="ctrl",
                collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
                ingest_timestamp_us=1_000_100, provenance=self.prov(),
            )

    def test_hmac_key_empty_bytes_rejected(self):
        with self.assertRaises(ValueError):
            create_collection_session(
                hmac_key=b"", session_controller_id="ctrl",
                collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
                ingest_timestamp_us=1_000_100, provenance=self.prov(),
            )

    def test_hmac_key_string_rejected(self):
        with self.assertRaises(ValueError):
            create_collection_session(
                hmac_key="not-bytes", session_controller_id="ctrl",
                collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
                ingest_timestamp_us=1_000_100, provenance=self.prov(),
            )

    def test_provenance_must_be_route_session_provenance(self):
        with self.assertRaises(ValueError):
            CollectionSessionV1(
                schema_version="1.0", record_kind="collection_session",
                collection_session_id="csn_v1_" + "a" * 64,
                session_controller_id="ctrl", collection_session_reference="ref",
                opened_source_timestamp_us=1_000_000,
                time_basis="source_timestamp_us", boundary_policy="explicit_half_open_v1",
                ingest_timestamp_us=1_000_100, provenance="not-a-provenance-object",
            )

    def test_collection_session_validation_type_check(self):
        with self.assertRaises(ValueError):
            validate_collection_session_boundaries("not-a-session")

    def test_membership_validation_type_check(self):
        with self.assertRaises(ValueError):
            validate_source_membership_boundaries("not-a-membership")

    def test_admission_wrong_session_type(self):
        with self.assertRaises(ValueError):
            validate_source_record_admission("not-a-session", "not-a-membership", 1_000_000)

    def test_analysis_type_validation_empty(self):
        with self.assertRaises(ValueError):
            create_analysis_session(
                hmac_key=ROUTE_KEY, analysis_type="", analysis_version="1.0",
                collection_session_ids=["csn_v1_" + "a" * 64],
                route_ids=[], input_manifest_digest="c" * 64,
                provenance=self.prov(operation_mode="analysis"),
                created_ingest_timestamp_us=2_000_000,
            )

    def test_overlap_invalid_type(self):
        with self.assertRaises(ValueError):
            validate_no_membership_overlap([("not-a-membership", None)])

    def test_overlap_wrong_close_type(self):
        session = create_collection_session(
            hmac_key=ROUTE_KEY, session_controller_id="ctrl",
            collection_session_reference="ref", opened_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        membership = create_source_membership(
            hmac_key=ROUTE_KEY, collection_session=session,
            source_type="synthetic.gps", sensor_id="sensor_a",
            source_instance_reference="inst_001", joined_source_timestamp_us=1_000_000,
            ingest_timestamp_us=1_000_100, provenance=self.prov(),
        )
        with self.assertRaises(ValueError):
            validate_no_membership_overlap([(membership, "not-a-close")])


if __name__ == "__main__":
    unittest.main()
