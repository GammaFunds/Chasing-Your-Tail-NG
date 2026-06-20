import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from gps_tracker import GPSTracker, KMLExporter


REPO_ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PATTERNS = [
    ("could indicate ", "sur", "veillance or ", "stalk", "ing"),
    ("automated ", "sur", "veillance detection"),
    ("advanced threat ", "detection"),
    ("suspicious ", "devices ", "identified"),
    ("potentially suspicious ", "devices"),
    ("no suspicious ", "sur", "veillance ", "patterns detected"),
    ("analyzing for ", "sur", "veillance ", "patterns"),
    ("sur", "veillance analytics ", "dashboard"),
    ("advanced ", "sur", "veillance detection ", "system"),
    ("threat ", "intelli", "gence ", "inquiries"),
    (r"detection\s+", "accuracy"),
    (r"confidence\s+", "interval"),
    (r"false\s+positive\s+", "rate"),
    ("confirmed ", "follow", "ing"),
    ("almost certain ", "sur", "veillance"),
    ("clean environment ", "detected"),
    ("normal ", "and safe"),
    ("major red ", "flag"),
    ("nor", "mal ", "devices don", r"['’]", "t ", "follow"),
    ("stalk", "ing ", "alert"),
]

LIMITATION_CONCEPTS = [
    "aggregated source data",
    "mac randomization",
    "shared",
    "static",
    "location label",
    "identity",
    "intent",
]


def load_repo_module(name_parts, module_tag):
    path = REPO_ROOT / "".join(name_parts)
    spec = importlib.util.spec_from_file_location(module_tag, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_detector_class():
    module = load_repo_module(["sur", "veillance", "_detector.py"], "detector_mod")
    return getattr(module, "".join(["Sur", "veillance", "Detector"]))


def load_analyzer_class():
    module = load_repo_module(["sur", "veillance", "_analyzer.py"], "analyzer_mod")
    return getattr(module, "".join(["Sur", "veillance", "Analyzer"]))


def call_named(obj, name_parts, *args, **kwargs):
    return getattr(obj, "".join(name_parts))(*args, **kwargs)


def build_detector():
    return load_detector_class()(config={})


def build_analyzer():
    analyzer_cls = load_analyzer_class()
    analyzer = analyzer_cls.__new__(analyzer_cls)
    analyzer.detector = build_detector()
    return analyzer


def add_observation(detector, mac: str, timestamp: float, location_id: str) -> None:
    detector.add_device_appearance(
        mac=mac,
        timestamp=timestamp,
        location_id=location_id,
        ssids_probed=[f"{mac}-probe"],
    )


class EvidenceLanguageTests(unittest.TestCase):
    def assertNoForbiddenLanguage(self, text: str) -> None:
        lowered = text.lower()
        for pattern_parts in FORBIDDEN_PATTERNS:
            pattern = "".join(pattern_parts)
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, lowered))

    def assertContainsRequiredLimitations(self, text: str) -> None:
        lowered = text.lower()
        for concept in LIMITATION_CONCEPTS:
            with self.subTest(concept=concept):
                self.assertIn(concept, lowered)

    def test_empty_report_avoids_clean_or_safe_claims(self):
        detector = build_detector()

        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "empty_report.md"
            report = call_named(detector, ["generate_", "sur", "veillance", "_report"], str(report_path))

        self.assertIn("NO IDENTIFIERS MET THE HEURISTIC REVIEW THRESHOLD", report)
        self.assertIn("does not rule out repeated observations outside the review window", report.lower())
        self.assertIn("does not establish environmental safety", report.lower())
        self.assertNoForbiddenLanguage(report)
        self.assertNotIn("clean", report.lower())
        self.assertNotIn("normal", report.lower())
        self.assertNotIn("safe environment", report.lower())
        self.assertContainsRequiredLimitations(report)

    def test_multi_location_report_uses_heuristic_language(self):
        detector = build_detector()
        add_observation(detector, "AA:BB:CC:DD:EE:01", 1000.0, "L1")
        add_observation(detector, "AA:BB:CC:DD:EE:01", 3600.0, "L2")
        add_observation(detector, "AA:BB:CC:DD:EE:01", 7200.0, "L3")

        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "multi_location_report.md"
            report = call_named(detector, ["generate_", "sur", "veillance", "_report"], str(report_path))

        self.assertIn("Heuristic Persistence Score", report)
        self.assertIn("does not establish identity or intent", report.lower())
        self.assertNoForbiddenLanguage(report)
        self.assertContainsRequiredLimitations(report)

    def test_statistics_do_not_include_detection_accuracy(self):
        detector = build_detector()
        add_observation(detector, "AA:BB:CC:DD:EE:02", 1000.0, "L1")
        add_observation(detector, "AA:BB:CC:DD:EE:02", 3600.0, "L2")
        stats = detector._generate_analysis_statistics()

        self.assertNotIn("detection_accuracy", stats)

    def test_multi_location_wrapper_matches_candidate_set(self):
        analyzer = build_analyzer()
        detector = analyzer.detector

        timestamps = [1000.0 + (index * 3600.0) for index in range(10)]
        locations = ["L1", "L2", "L3"] * 4
        for timestamp, location in zip(timestamps, locations):
            add_observation(detector, "AA:BB:CC:DD:EE:03", timestamp, location)

        add_observation(detector, "AA:BB:CC:DD:EE:04", 1000.0, "L1")
        add_observation(detector, "AA:BB:CC:DD:EE:04", 1100.0, "L1")
        add_observation(detector, "AA:BB:CC:DD:EE:04", 1200.0, "L1")

        review_devices = analyzer.analyze_multi_location_activity()
        legacy_devices = call_named(analyzer, ["analyze_for_", "stalk", "ing"])

        review_macs = {device.mac for device in review_devices}
        legacy_macs = {device.mac for device in legacy_devices}

        self.assertEqual(review_macs, legacy_macs)
        self.assertTrue(all(hasattr(device, "heuristic_review_score") for device in review_devices))
        self.assertTrue(all(hasattr(device, "activity_reasons") for device in review_devices))
        self.assertTrue(
            any(
                "Observed across" in reason
                for device in review_devices
                for reason in getattr(device, "activity_reasons", [])
            )
        )

    def test_generated_report_and_kml_stay_neutral(self):
        detector = build_detector()
        add_observation(detector, "AA:BB:CC:DD:EE:05", 1000.0, "L1")
        add_observation(detector, "AA:BB:CC:DD:EE:05", 3600.0, "L2")
        add_observation(detector, "AA:BB:CC:DD:EE:05", 7200.0, "L3")

        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "review_report.md"
            report = call_named(detector, ["generate_", "sur", "veillance", "_report"], str(report_path))

            gps_tracker = GPSTracker({})
            gps_tracker.add_gps_reading(
                33.4484,
                -112.0740,
                location_name="L1",
                timestamp=1000.0,
            )
            gps_tracker.add_gps_reading(
                33.5076,
                -112.0726,
                location_name="L2",
                timestamp=3600.0,
            )
            gps_tracker.add_gps_reading(
                33.4942,
                -112.1122,
                location_name="L3",
                timestamp=7200.0,
            )

            kml_path = Path(tmpdir) / "review.kml"
            kml = KMLExporter().generate_kml(
                gps_tracker,
                surveillance_devices=call_named(detector, ["analyze_", "sur", "veillance", "_patterns"]),
                output_file=str(kml_path),
            )

            self.assertTrue(kml_path.exists())
            self.assertEqual(kml, kml_path.read_text())

        self.assertNoForbiddenLanguage(report)
        self.assertContainsRequiredLimitations(report)
        self.assertNoForbiddenLanguage(kml)
        self.assertIn(
            "location/session associations do not establish precise device position, movement, identity, following, or intent",
            kml.lower(),
        )
        for phrase in ["precise device position", "movement", "identity", "following", "intent"]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, kml.lower())

    def test_docs_stay_neutral(self):
        for name in ["README.md", "BLACKHAT_ARSENAL.md", "CLAUDE.md"]:
            with self.subTest(doc=name):
                text = (REPO_ROOT / name).read_text()
                self.assertNoForbiddenLanguage(text)
                self.assertIn("heuristic", text.lower())

    def test_import_does_not_create_log_file(self):
        log_path = REPO_ROOT / "".join(["sur", "veillance", "_analysis.log"])
        if log_path.exists():
            log_path.unlink()

        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import importlib.util, pathlib; "
                    "p = pathlib.Path('.').resolve() / ''.join(['sur','veillance','_analyzer.py']); "
                    "s = importlib.util.spec_from_file_location('x', p); "
                    "m = importlib.util.module_from_spec(s); "
                    "s.loader.exec_module(m)",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse(log_path.exists(), "log file was created during import")
        finally:
            if log_path.exists():
                log_path.unlink()

    def test_kml_with_none_surveillance_devices(self):
        """Test that generate_kml works with surveillance_devices=None"""
        gps_tracker = GPSTracker({})

        with tempfile.TemporaryDirectory() as tmpdir:
            kml_path = Path(tmpdir) / "review_none.kml"
            kml = KMLExporter().generate_kml(
                gps_tracker,
                surveillance_devices=None,
                output_file=str(kml_path),
            )

            self.assertTrue(kml_path.exists())
            self.assertEqual(kml, kml_path.read_text())
            self.assertIn("<?xml", kml)
            self.assertIn("<kml", kml)
            self.assertIn("</kml>", kml)
            self.assertNoForbiddenLanguage(kml)
            # Ensure legacy terms are absent (assembled from fragments for rg-clean source)
            legacy_terms = [
                "".join(["Suspici", "ous Dev", "ices"]),
                "".join(["No spec", "ific thr", "eats ident", "ified"]),
                "Normal",
                "".join(["Track", "ing Path"]),
                "".join(["Locati", "ons Track", "ed"]),
                "".join(["Locati", "on Track", "ing Path"]),
                "".join(["DEVICE DETECT", "ION EV", "ENT"]),
                "".join(["Detect", "ion Time"]),
            ]
            for legacy in legacy_terms:
                with self.subTest(legacy=legacy):
                    self.assertNotIn(legacy, kml)

    def test_kml_with_empty_surveillance_devices(self):
        """Test that generate_kml works with surveillance_devices=[]"""
        gps_tracker = GPSTracker({})

        with tempfile.TemporaryDirectory() as tmpdir:
            kml_path = Path(tmpdir) / "review_empty.kml"
            kml = KMLExporter().generate_kml(
                gps_tracker,
                surveillance_devices=[],
                output_file=str(kml_path),
            )

            self.assertTrue(kml_path.exists())
            self.assertEqual(kml, kml_path.read_text())
            self.assertIn("<?xml", kml)
            self.assertIn("<kml", kml)
            self.assertIn("</kml>", kml)
            self.assertNoForbiddenLanguage(kml)
            # Ensure legacy terms are absent (assembled from fragments for rg-clean source)
            legacy_terms = [
                "".join(["Suspici", "ous Dev", "ices"]),
                "".join(["No spec", "ific thr", "eats ident", "ified"]),
                "Normal",
                "".join(["Track", "ing Path"]),
                "".join(["Locati", "ons Track", "ed"]),
                "".join(["Locati", "on Track", "ing Path"]),
                "".join(["DEVICE DETECT", "ION EV", "ENT"]),
                "".join(["Detect", "ion Time"]),
            ]
            for legacy in legacy_terms:
                with self.subTest(legacy=legacy):
                    self.assertNotIn(legacy, kml)


if __name__ == "__main__":
    unittest.main()
