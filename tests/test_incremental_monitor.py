import io
import unittest
from unittest.mock import patch

import secure_main_logic
from secure_main_logic import SecureCYTMonitor


class FakeDB:
    def __init__(self, rows):
        self.rows = rows

    def get_devices_by_time_range(self, start_time, end_time=None):
        return list(self.rows)


def make_monitor(ssid_ignore_list=None):
    config = {}
    monitor = SecureCYTMonitor(config, [], ssid_ignore_list or [], io.StringIO())
    monitor.five_ten_min_ago_macs = {"AA:BB:CC:DD:EE:FF"}
    monitor.ten_fifteen_min_ago_macs = set()
    monitor.fifteen_twenty_min_ago_macs = set()
    monitor.five_ten_min_ago_ssids = {"Probe-1"}
    monitor.ten_fifteen_min_ago_ssids = set()
    monitor.fifteen_twenty_min_ago_ssids = set()
    return monitor


def row(mac, last_time, ssid="Probe-1"):
    return {
        "mac": mac,
        "last_time": last_time,
        "device_data": {
            "dot11.device": {
                "dot11.device.last_probed_ssid_record": {
                    "dot11.probedssid.ssid": ssid,
                }
            }
        },
    }


class IncrementalMonitorTests(unittest.TestCase):
    @patch.object(secure_main_logic.SecureTimeWindows, "get_time_boundaries", return_value={"current_time": 0.0})
    def test_same_row_three_polls_then_newer_last_time(self, _boundaries):
        monitor = make_monitor()
        log_file = monitor.log_file

        with patch.object(secure_main_logic.logger, "warning") as warning_mock:
            monitor.process_current_activity(FakeDB([row("aa:bb:cc:dd:ee:ff", 100.0)]))
            monitor.process_current_activity(FakeDB([row("AA:BB:CC:DD:EE:FF", 100.0)]))
            monitor.process_current_activity(FakeDB([row("aa:bb:cc:dd:ee:ff", 100.0)]))

            self.assertEqual(log_file.getvalue().count("Found a probe!: Probe-1"), 1)
            self.assertEqual(log_file.getvalue().count("Probe for Probe-1 in 5 to 10 mins list"), 1)
            self.assertEqual(log_file.getvalue().count("AA:BB:CC:DD:EE:FF in 5 to 10 mins list"), 1)
            self.assertEqual(warning_mock.call_count, 2)
            self.assertEqual(len(monitor._processed_rows), 1)

            monitor.process_current_activity(FakeDB([row("aa:bb:cc:dd:ee:ff", 101.0)]))

        output = log_file.getvalue()
        self.assertEqual(output.count("Found a probe!: Probe-1"), 2)
        self.assertEqual(output.count("Probe for Probe-1 in 5 to 10 mins list"), 2)
        self.assertEqual(output.count("AA:BB:CC:DD:EE:FF in 5 to 10 mins list"), 2)
        self.assertEqual(warning_mock.call_count, 4)
        self.assertEqual(len(monitor._processed_rows), 2)

    @patch.object(secure_main_logic.SecureTimeWindows, "get_time_boundaries", return_value={"current_time": 0.0})
    def test_large_active_window_does_not_evict_first_row(self, _boundaries):
        monitor = make_monitor(ssid_ignore_list=["ignored"])
        first_row = row("AA:BB:CC:DD:EE:FF", 100.0, ssid="ignored")
        many_rows = [first_row]
        for index in range(1, 4105):
            mac = f"00:11:22:33:{index // 256:02X}:{index % 256:02X}"
            many_rows.append(row(mac, 100.0, ssid="ignored"))

        with patch.object(secure_main_logic.logger, "warning") as warning_mock:
            monitor.process_current_activity(FakeDB(many_rows))
            monitor.process_current_activity(FakeDB([first_row]))

        self.assertEqual(warning_mock.call_count, 1)
        self.assertEqual(monitor.log_file.getvalue().count("AA:BB:CC:DD:EE:FF in 5 to 10 mins list"), 1)
        self.assertEqual(len(monitor._processed_rows), len(many_rows))

    @patch.object(secure_main_logic.SecureTimeWindows, "get_time_boundaries", return_value={"current_time": 100.0})
    def test_time_window_prunes_only_older_keys(self, _boundaries):
        monitor = make_monitor()
        monitor._processed_rows = {
            ("AA:BB:CC:DD:EE:01", 99.0): None,
            ("AA:BB:CC:DD:EE:02", 100.0): None,
            ("AA:BB:CC:DD:EE:03", 101.0): None,
        }

        monitor._prune_processed_rows(100.0)

        self.assertNotIn(("AA:BB:CC:DD:EE:01", 99.0), monitor._processed_rows)
        self.assertIn(("AA:BB:CC:DD:EE:02", 100.0), monitor._processed_rows)
        self.assertIn(("AA:BB:CC:DD:EE:03", 101.0), monitor._processed_rows)

    @patch.object(secure_main_logic.SecureTimeWindows, "get_time_boundaries", return_value={"current_time": 0.0})
    def test_invalid_last_time_values_do_not_enter_cache(self, _boundaries):
        invalid_values = (None, "not-a-number", float("nan"), float("inf"), float("-inf"))
        for invalid_last_time in invalid_values:
            monitor = make_monitor()
            with self.subTest(invalid_last_time=invalid_last_time):
                monitor.process_current_activity(FakeDB([row("00:11:22:33:44:55", invalid_last_time)]))
                monitor.process_current_activity(FakeDB([row("00:11:22:33:44:55", invalid_last_time)]))
                self.assertEqual(len(monitor._processed_rows), 0)
                self.assertEqual(
                    monitor.log_file.getvalue().count("Found a probe!: Probe-1"),
                    2,
                )

    @patch.object(secure_main_logic.SecureTimeWindows, "get_time_boundaries", return_value={"current_time": 0.0})
    def test_distinct_rows_inside_window_remain_cached(self, _boundaries):
        monitor = make_monitor(ssid_ignore_list=["ignored"])
        monitor.process_current_activity(
            FakeDB(
                [
                    row("00:11:22:33:44:55", 1.0, ssid="ignored"),
                    row("00:11:22:33:44:66", 2.0, ssid="ignored"),
                    row("00:11:22:33:44:77", 3.0, ssid="ignored"),
                ]
            )
        )

        self.assertEqual(len(monitor._processed_rows), 3)


if __name__ == "__main__":
    unittest.main()
