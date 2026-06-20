import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from gps_tracker import GPSTracker
from surveillance_analyzer import SurveillanceAnalyzer
from surveillance_detector import SurveillanceDetector


def make_analyzer(max_delta_seconds: float = 30.0) -> SurveillanceAnalyzer:
    config = {
        "gps": {
            "max_correlation_delta_seconds": max_delta_seconds,
        }
    }

    analyzer = SurveillanceAnalyzer.__new__(SurveillanceAnalyzer)
    analyzer.config = config
    analyzer.detector = SurveillanceDetector(config)
    analyzer.gps_tracker = GPSTracker(config)
    return analyzer


class GPSSourceTimeTests(unittest.TestCase):
    def test_gps_reading_requires_explicit_source_timestamp(self):
        tracker = GPSTracker({})

        with self.assertRaises(ValueError):
            tracker.add_gps_reading(
                51.5000,
                7.4000,
                location_name="Untimed",
            )

    def test_gps_timestamp_and_session_times_preserve_source_time(self):
        tracker = GPSTracker({})

        first_session_id = tracker.add_gps_reading(
            51.5000,
            7.4000,
            timestamp=1000.25,
            accuracy=4.5,
            location_name="Alpha",
        )
        second_session_id = tracker.add_gps_reading(
            51.5001,
            7.4001,
            timestamp=1010.75,
            accuracy=5.5,
            location_name="Alpha",
        )

        self.assertEqual(first_session_id, second_session_id)
        self.assertEqual(
            [location.timestamp for location in tracker.locations],
            [1000.25, 1010.75],
        )

        session = tracker.location_sessions[0]
        self.assertEqual(session.start_time, 1000.25)
        self.assertEqual(session.end_time, 1010.75)

    def test_exact_match_preserves_gps_metadata(self):
        tracker = GPSTracker({})

        session_id = tracker.add_gps_reading(
            51.5100,
            7.4100,
            timestamp=2000.0,
            accuracy=3.0,
            location_name="Exact",
        )

        correlation = tracker.correlate_timestamp(2000.0)

        self.assertIsNotNone(correlation)
        self.assertEqual(correlation.location_id, session_id)
        self.assertEqual(correlation.gps_timestamp, 2000.0)
        self.assertEqual(correlation.latitude, 51.5100)
        self.assertEqual(correlation.longitude, 7.4100)
        self.assertEqual(correlation.accuracy, 3.0)
        self.assertEqual(correlation.source_to_fix_delta_ms, 0.0)

    def test_bounded_match_uses_signed_delta(self):
        tracker = GPSTracker(
            {"gps": {"max_correlation_delta_seconds": 30.0}}
        )
        tracker.add_gps_reading(
            51.5200,
            7.4200,
            timestamp=3010.0,
            location_name="Bounded",
        )

        correlation = tracker.correlate_timestamp(3000.0)

        self.assertIsNotNone(correlation)
        self.assertEqual(
            correlation.source_to_fix_delta_ms,
            10000.0,
        )

    def test_equal_distance_tie_prefers_earlier_fix(self):
        tracker = GPSTracker(
            {"gps": {"max_correlation_delta_seconds": 30.0}}
        )
        earlier_session = tracker.add_gps_reading(
            51.5300,
            7.4300,
            timestamp=3990.0,
            location_name="Earlier",
        )
        tracker.add_gps_reading(
            51.5400,
            7.4400,
            timestamp=4010.0,
            location_name="Later",
        )

        correlation = tracker.correlate_timestamp(4000.0)

        self.assertIsNotNone(correlation)
        self.assertEqual(correlation.location_id, earlier_session)
        self.assertEqual(correlation.gps_timestamp, 3990.0)
        self.assertEqual(
            correlation.source_to_fix_delta_ms,
            -10000.0,
        )

    def test_out_of_window_match_remains_unknown(self):
        tracker = GPSTracker(
            {"gps": {"max_correlation_delta_seconds": 30.0}}
        )
        tracker.add_gps_reading(
            51.5500,
            7.4500,
            timestamp=5000.0,
            location_name="TooFar",
        )

        self.assertIsNone(tracker.correlate_timestamp(5030.001))

    def test_missing_accuracy_remains_none(self):
        tracker = GPSTracker({})
        tracker.add_gps_reading(
            51.5600,
            7.4600,
            timestamp=6000.0,
            location_name="NoAccuracy",
        )

        correlation = tracker.correlate_timestamp(6000.0)

        self.assertIsNotNone(correlation)
        self.assertIsNone(correlation.accuracy)

    def test_out_of_order_fixes_extend_same_session_by_source_time(self):
        tracker = GPSTracker({})

        later_session_id = tracker.add_gps_reading(
            51.5650,
            7.4650,
            timestamp=9010.0,
            location_name="OutOfOrder",
        )
        earlier_session_id = tracker.add_gps_reading(
            51.5650,
            7.4650,
            timestamp=9000.0,
            location_name="OutOfOrder",
        )

        self.assertEqual(
            later_session_id,
            earlier_session_id,
        )
        self.assertEqual(len(tracker.location_sessions), 1)

        session = tracker.location_sessions[0]
        self.assertEqual(session.start_time, 9000.0)
        self.assertEqual(session.end_time, 9010.0)
        self.assertEqual(session.location.timestamp, 9000.0)

    def test_out_of_order_bridge_fix_coalesces_adjacent_sessions(self):
        tracker = GPSTracker({})

        first_session_id = tracker.add_gps_reading(
            51.5670,
            7.4670,
            timestamp=1000.0,
            location_name="Bridge",
        )
        tracker.add_device_to_session(
            "device-alpha",
            first_session_id,
        )

        second_session_id = tracker.add_gps_reading(
            51.5670,
            7.4670,
            timestamp=2200.0,
            location_name="Bridge",
        )
        tracker.add_device_to_session(
            "device-beta",
            second_session_id,
        )

        self.assertNotEqual(
            first_session_id,
            second_session_id,
        )

        bridge_session_id = tracker.add_gps_reading(
            51.5670,
            7.4670,
            timestamp=1600.0,
            location_name="Bridge",
        )

        self.assertEqual(
            len(tracker.location_sessions),
            1,
            "session partition must not depend on GPS ingest order",
        )

        session = tracker.location_sessions[0]

        self.assertEqual(
            bridge_session_id,
            session.session_id,
        )
        self.assertEqual(session.start_time, 1000.0)
        self.assertEqual(session.end_time, 2200.0)
        self.assertEqual(
            set(session.devices_seen),
            {
                "device-alpha",
                "device-beta",
            },
        )
        self.assertEqual(
            {
                location.session_id
                for location in tracker.locations
            },
            {session.session_id},
        )

    def test_same_cluster_revisit_after_timeout_gets_unique_session(self):
        tracker = GPSTracker({})

        first_session_id = tracker.add_gps_reading(
            51.5700,
            7.4700,
            timestamp=7000.0,
            location_name="Revisit",
        )
        second_session_id = tracker.add_gps_reading(
            51.5700,
            7.4700,
            timestamp=7601.0,
            location_name="Revisit",
        )

        self.assertNotEqual(first_session_id, second_session_id)
        self.assertEqual(len(tracker.location_sessions), 2)
        self.assertEqual(
            tracker.location_sessions[0].cluster_id,
            tracker.location_sessions[1].cluster_id,
        )


class KismetGPSCorrelationFixtureTests(unittest.TestCase):
    def test_packets_altitude_column_is_optional(self):
        analyzer = make_analyzer()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "no-altitude.kismet"

            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE packets (
                        ts_sec INTEGER,
                        ts_usec INTEGER,
                        lat REAL,
                        lon REAL
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO packets
                        (ts_sec, ts_usec, lat, lon)
                    VALUES
                        (?, ?, ?, ?)
                    """,
                    (9100, 250000, 51.5900, 7.4900),
                )
                connection.commit()

            gps_count = analyzer._load_gps_fixes_from_kismet(
                str(db_path)
            )

        self.assertEqual(gps_count, 1)
        self.assertEqual(
            analyzer.gps_tracker.locations[0].timestamp,
            9100.25,
        )
        self.assertIsNone(
            analyzer.gps_tracker.locations[0].altitude
        )

    def test_packets_gps_fixes_correlate_devices_last_time(self):
        analyzer = make_analyzer()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "fixture.kismet"

            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE packets (
                        ts_sec INTEGER,
                        ts_usec INTEGER,
                        lat REAL,
                        lon REAL,
                        alt REAL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE devices (
                        devmac TEXT,
                        last_time REAL,
                        type TEXT,
                        device TEXT
                    )
                    """
                )

                connection.execute(
                    """
                    INSERT INTO packets
                        (ts_sec, ts_usec, lat, lon, alt)
                    VALUES
                        (?, ?, ?, ?, ?)
                    """,
                    (8000, 500000, 51.5800, 7.4800, 100.0),
                )

                connection.execute(
                    """
                    INSERT INTO devices
                        (devmac, last_time, type, device)
                    VALUES
                        (?, ?, ?, ?)
                    """,
                    (
                        "02:00:00:00:00:01",
                        8000.4,
                        "Wi-Fi Client",
                        json.dumps({}),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO devices
                        (devmac, last_time, type, device)
                    VALUES
                        (?, ?, ?, ?)
                    """,
                    (
                        "02:00:00:00:00:02",
                        8100.0,
                        "Wi-Fi Client",
                        json.dumps({}),
                    ),
                )
                connection.commit()

            gps_count = analyzer._load_gps_fixes_from_kismet(
                str(db_path)
            )
            device_count = analyzer._load_appearances_with_gps(
                str(db_path)
            )

        self.assertEqual(gps_count, 1)
        self.assertEqual(device_count, 2)

        matched = analyzer.detector.device_history[
            "02:00:00:00:00:01"
        ][0]
        unmatched = analyzer.detector.device_history[
            "02:00:00:00:00:02"
        ][0]

        self.assertNotEqual(
            matched.location_id,
            "unknown_location",
        )
        self.assertEqual(matched.gps_timestamp, 8000.5)
        self.assertEqual(matched.gps_latitude, 51.5800)
        self.assertEqual(matched.gps_longitude, 7.4800)
        self.assertIsNone(matched.gps_accuracy)
        self.assertAlmostEqual(
            matched.source_to_fix_delta_ms,
            100.0,
            places=6,
        )

        self.assertEqual(
            unmatched.location_id,
            "unknown_location",
        )
        self.assertIsNone(unmatched.gps_timestamp)
        self.assertIsNone(unmatched.gps_latitude)
        self.assertIsNone(unmatched.gps_longitude)
        self.assertIsNone(unmatched.gps_accuracy)
        self.assertIsNone(
            unmatched.source_to_fix_delta_ms
        )

        matched_session = next(
            session
            for session in analyzer.gps_tracker.location_sessions
            if session.session_id == matched.location_id
        )
        self.assertIn(
            "02:00:00:00:00:01",
            matched_session.devices_seen,
        )
        self.assertNotIn(
            "02:00:00:00:00:02",
            matched_session.devices_seen,
        )


if __name__ == "__main__":
    unittest.main()
