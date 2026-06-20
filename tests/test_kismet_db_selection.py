import json
import os
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import secure_database
from secure_database import (
    SecureKismetDB,
    find_newest_matching_kismet_db,
    select_runtime_kismet_db,
)


def make_valid_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE devices (devmac TEXT, type TEXT, device TEXT, last_time REAL)"
        )
        connection.commit()
    finally:
        connection.close()


def make_invalid_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        pass
    finally:
        connection.close()


def set_mtime(path: Path, mtime: float) -> None:
    os.utime(path, (mtime, mtime))


class KismetDbSelectionTests(unittest.TestCase):
    def test_newest_helper_selects_correct_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            old_path = root / "old.kismet"
            mid_path = root / "mid.kismet"
            new_path = root / "new.kismet"

            make_valid_db(old_path)
            make_valid_db(mid_path)
            make_valid_db(new_path)

            set_mtime(old_path, 1000.0)
            set_mtime(mid_path, 2000.0)
            set_mtime(new_path, 3000.0)

            selected = find_newest_matching_kismet_db(str(root / "*.kismet"))
            self.assertEqual(selected, new_path)

    def test_empty_discovery_retains_current_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            current_path = root / "current.kismet"
            make_valid_db(current_path)

            with self.assertLogs("secure_database", level="WARNING") as logs:
                selected_path, switched = select_runtime_kismet_db(str(current_path), str(root / "*.missing"))

            self.assertEqual(selected_path, current_path)
            self.assertFalse(switched)
            self.assertTrue(any("No Kismet database candidates matched pattern" in line for line in logs.output))

    def test_valid_rotation_switches_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            current_path = root / "current.kismet"
            candidate_path = root / "candidate.kismet"

            make_valid_db(current_path)
            make_valid_db(candidate_path)
            set_mtime(current_path, 1000.0)
            set_mtime(candidate_path, 2000.0)

            with self.assertLogs("secure_database", level="INFO") as logs:
                selected_path, switched = select_runtime_kismet_db(str(current_path), str(root / "*.kismet"))
                selected_path_again, switched_again = select_runtime_kismet_db(str(selected_path), str(root / "*.kismet"))

            self.assertEqual(selected_path, candidate_path)
            self.assertTrue(switched)
            self.assertEqual(selected_path_again, candidate_path)
            self.assertFalse(switched_again)
            self.assertEqual(sum("Using Kismet database:" in line for line in logs.output), 1)

    def test_invalid_candidate_keeps_current_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            current_path = root / "current.kismet"
            candidate_path = root / "candidate.kismet"

            make_valid_db(current_path)
            make_invalid_db(candidate_path)
            set_mtime(current_path, 1000.0)
            set_mtime(candidate_path, 2000.0)

            with self.assertLogs("secure_database", level="WARNING") as logs:
                selected_path, switched = select_runtime_kismet_db(str(current_path), str(root / "*.kismet"))

            self.assertEqual(selected_path, current_path)
            self.assertFalse(switched)
            self.assertTrue(any("failed validation" in line for line in logs.output))

    def test_unopenable_candidate_keeps_current_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            current_path = root / "current.kismet"
            candidate_path = root / "candidate.kismet"

            make_valid_db(current_path)
            make_valid_db(candidate_path)
            set_mtime(current_path, 1000.0)
            set_mtime(candidate_path, 2000.0)

            with patch.object(secure_database.sqlite3, "connect", side_effect=sqlite3.OperationalError("boom")):
                with self.assertLogs("secure_database", level="WARNING") as logs:
                    selected_path, switched = select_runtime_kismet_db(str(current_path), str(root / "*.kismet"))

            self.assertEqual(selected_path, current_path)
            self.assertFalse(switched)
            self.assertTrue(any("could not be opened or validated" in line for line in logs.output))

    def test_config_uses_json_ignore_lists(self):
        with open("config.json", "r", encoding="utf-8") as handle:
            config = json.load(handle)

        self.assertEqual(config["paths"]["ignore_lists"]["mac"], "mac_list.json")
        self.assertEqual(config["paths"]["ignore_lists"]["ssid"], "ssid_list.json")


if __name__ == "__main__":
    unittest.main()
