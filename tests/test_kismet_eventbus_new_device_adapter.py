"""Deterministic tests for KismetEventbusNewDeviceAdapter.

No real WebSocket transport, ObservationStore, filesystem, or network
is used.  All tests are pure decode → assertion.
"""

from __future__ import annotations

import ast
import hashlib
import hmac
import json
import unittest
from dataclasses import FrozenInstanceError

from observation_contract import ObservationEventV1
from kismet_eventbus_new_device_adapter import (
    KismetEventbusNewDeviceAdapterError,
    NEW_DEVICE,
    decode_kismet_new_device_envelope,
)


class KismetEventbusNewDeviceAdapterTests(unittest.TestCase):
    """Decode-envelope tests for the Kismet eventbus NEW_DEVICE adapter."""

    KEY = b"test-hmac-key-32-bytes-long!!"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _payload(**fields):
        data = {
            "kismet.device.base.key": "AA:BB:CC:DD:EE:FF",
            "kismet.device.base.macaddr": "AA:BB:CC:DD:EE:FF",
            "kismet.device.base.first_time": 1234567890,
        }
        data.update(fields)
        return data

    @staticmethod
    def _envelope(**fields):
        return {NEW_DEVICE: KismetEventbusNewDeviceAdapterTests._payload(**fields)}

    def _decode(self, envelope=None, **overrides):
        if envelope is None:
            envelope = self._envelope()
        args = {
            "hmac_key": self.KEY,
            "collection_session_id": "session_alpha",
            "sensor_id": "sensor_alpha",
            "ingest_timestamp_us": 1_000_500,
        }
        args.update(overrides)
        return decode_kismet_new_device_envelope(envelope, **args)

    @staticmethod
    def _canonical_identity_bytes(parts):
        return json.dumps(
            list(parts),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    def _expected_observation_id(self, source_type, sensor_id, session_id,
                                 source_record_reference):
        identity_bytes = self._canonical_identity_bytes(
            (source_type, sensor_id, session_id, source_record_reference)
        )
        digest = hmac.new(self.KEY, identity_bytes, hashlib.sha256).hexdigest()
        return f"obs_v1_{digest}"

    # ------------------------------------------------------------------
    # 1. Valid minimal envelope
    # ------------------------------------------------------------------

    def test_valid_minimal_envelope_produces_expected_fields(self):
        event = self._decode()
        expected_ref = json.dumps(
            ["kismet.eventbus.new-device.v1", "AA:BB:CC:DD:EE:FF", 1234567890],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        expected_id = self._expected_observation_id(
            "kismet.eventbus.new_device",
            "sensor_alpha",
            "session_alpha",
            expected_ref,
        )

        self.assertEqual(event.schema_version, "1.0")
        self.assertEqual(event.record_kind, "observation_event")
        self.assertEqual(event.observation_id, expected_id)
        self.assertEqual(event.collection_session_id, "session_alpha")
        self.assertEqual(event.source_type, "kismet.eventbus.new_device")
        self.assertEqual(event.sensor_id, "sensor_alpha")
        self.assertEqual(event.source_timestamp_us, 1234567890_000_000)
        self.assertEqual(event.ingest_timestamp_us, 1_000_500)
        self.assertEqual(event.source_record_reference, expected_ref)
        self.assertEqual(event.device_identifier, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(event.device_identifier_kind, "mac")
        self.assertIsNone(event.signal_strength)
        self.assertIsNone(event.signal_strength_unit)

        prov = event.provenance
        self.assertEqual(prov.collector_name, "cyt.kismet_eventbus_new_device_adapter")
        self.assertEqual(prov.collector_version, "1.0")
        self.assertEqual(prov.ingest_mode, "live")
        self.assertEqual(prov.source_schema_version, "kismet.eventbus.new-device.v1")

    # ------------------------------------------------------------------
    # 2. Same identity inputs produce the same observation_id
    # ------------------------------------------------------------------

    def test_same_identity_same_observation_id(self):
        a = self._decode()
        b = self._decode()
        self.assertEqual(a.observation_id, b.observation_id)
        self.assertEqual(a.source_record_reference, b.source_record_reference)
        self.assertEqual(a.source_timestamp_us, b.source_timestamp_us)

    # ------------------------------------------------------------------
    # 3. Changed device key changes source_record_reference and
    #    observation_id
    # ------------------------------------------------------------------

    def test_changed_device_key_changes_reference_and_id(self):
        a = self._decode(envelope=self._envelope(
            **{"kismet.device.base.key": "11:22:33:44:55:66"}
        ))
        b = self._decode(envelope=self._envelope(
            **{"kismet.device.base.key": "AA:BB:CC:DD:EE:FF"}
        ))
        self.assertNotEqual(a.source_record_reference, b.source_record_reference)
        self.assertNotEqual(a.observation_id, b.observation_id)

    # ------------------------------------------------------------------
    # 4. Changed collection_session_id or sensor_id changes
    #    observation_id
    # ------------------------------------------------------------------

    def test_changed_session_changes_observation_id(self):
        a = self._decode(collection_session_id="alpha")
        b = self._decode(collection_session_id="beta")
        self.assertNotEqual(a.observation_id, b.observation_id)

    def test_changed_sensor_changes_observation_id(self):
        a = self._decode(sensor_id="sensor_a")
        b = self._decode(sensor_id="sensor_b")
        self.assertNotEqual(a.observation_id, b.observation_id)

    # ------------------------------------------------------------------
    # 5. Changed ingest_timestamp_us does not change observation_id
    # ------------------------------------------------------------------

    def test_changed_ingest_timestamp_does_not_change_observation_id(self):
        a = self._decode(ingest_timestamp_us=1_000_000)
        b = self._decode(ingest_timestamp_us=9_999_999)
        self.assertEqual(a.observation_id, b.observation_id)
        self.assertNotEqual(a.ingest_timestamp_us, b.ingest_timestamp_us)

    # ------------------------------------------------------------------
    # 6. Extra payload fields are ignored
    # ------------------------------------------------------------------

    def test_extra_payload_fields_ignored(self):
        payload = self._payload()
        payload["extra_field"] = "should-be-ignored"
        payload["another_extra"] = 42
        event = self._decode(envelope={NEW_DEVICE: payload})
        self.assertEqual(
            event.source_record_reference,
            json.dumps(
                ["kismet.eventbus.new-device.v1", "AA:BB:CC:DD:EE:FF", 1234567890],
                ensure_ascii=True,
                separators=(",", ":"),
            ),
        )
        self.assertEqual(event.device_identifier, "AA:BB:CC:DD:EE:FF")

    # ------------------------------------------------------------------
    # 7. Invalid inputs all fail closed
    # ------------------------------------------------------------------

    def test_invalid_envelope_shapes_fail_closed(self):
        cases = [
            ("missing NEW_DEVICE key", {}),
            ("extra top-level topic", {NEW_DEVICE: self._payload(), "EXTRA": 1}),
            ("wrong envelope type: str", "not-a-dict"),
            ("wrong envelope type: list", ["NEW_DEVICE"]),
            ("wrong envelope type: int", 42),
            ("wrong envelope type: None", None),
        ]
        for label, env in cases:
            with self.subTest(label=label):
                args = {
                    "hmac_key": self.KEY,
                    "collection_session_id": "session_alpha",
                    "sensor_id": "sensor_alpha",
                    "ingest_timestamp_us": 1_000_500,
                }
                with self.assertRaises(KismetEventbusNewDeviceAdapterError):
                    decode_kismet_new_device_envelope(env, **args)

    def test_invalid_payload_type_fails_closed(self):
        for label, value in (
            ("string", "not-a-dict"),
            ("list", [1, 2, 3]),
            ("int", 42),
            ("float", 1.5),
            ("None", None),
        ):
            with self.subTest(payload_type=label):
                with self.assertRaises(KismetEventbusNewDeviceAdapterError):
                    self._decode(envelope={NEW_DEVICE: value})

    def test_missing_required_fields_fail_closed(self):
        base = self._payload()
        missing_cases = [
            ("missing device_key", {}, ["kismet.device.base.key"]),
            ("missing macaddr", {}, ["kismet.device.base.macaddr"]),
            ("missing first_time", {}, ["kismet.device.base.first_time"]),
        ]
        for label, _, remove_keys in missing_cases:
            with self.subTest(label=label):
                payload = dict(base)
                for k in remove_keys:
                    payload.pop(k, None)
                with self.assertRaises(KismetEventbusNewDeviceAdapterError):
                    self._decode(envelope={NEW_DEVICE: payload})

    def test_blank_key_fails_closed(self):
        with self.assertRaises(KismetEventbusNewDeviceAdapterError):
            self._decode(envelope=self._envelope(
                **{"kismet.device.base.key": ""}
            ))

    def test_blank_mac_fails_closed(self):
        with self.assertRaises(KismetEventbusNewDeviceAdapterError):
            self._decode(envelope=self._envelope(
                **{"kismet.device.base.macaddr": ""}
            ))

    def test_zero_mac_fails_closed(self):
        with self.assertRaises(KismetEventbusNewDeviceAdapterError):
            self._decode(envelope=self._envelope(
                **{"kismet.device.base.macaddr": "00:00:00:00:00:00"}
            ))

    def test_mac_with_whitespace_stripped(self):
        event = self._decode(envelope=self._envelope(
            **{"kismet.device.base.macaddr": "  AA:BB:CC:DD:EE:FF  "}
        ))
        self.assertEqual(event.device_identifier, "AA:BB:CC:DD:EE:FF")

    def test_mac_with_tab_and_newline_stripped(self):
        event = self._decode(envelope=self._envelope(
            **{"kismet.device.base.macaddr": "\tAA:BB:CC:DD:EE:FF\n"}
        ))
        self.assertEqual(event.device_identifier, "AA:BB:CC:DD:EE:FF")

    def test_whitespace_only_mac_rejected(self):
        with self.assertRaises(KismetEventbusNewDeviceAdapterError):
            self._decode(envelope=self._envelope(
                **{"kismet.device.base.macaddr": "   "}
            ))

    def test_zero_mac_with_whitespace_rejected(self):
        with self.assertRaises(KismetEventbusNewDeviceAdapterError):
            self._decode(envelope=self._envelope(
                **{"kismet.device.base.macaddr": "  00:00:00:00:00:00  "}
            ))

    def test_bool_first_time_fails_closed(self):
        with self.assertRaises(KismetEventbusNewDeviceAdapterError):
            self._decode(envelope=self._envelope(
                **{"kismet.device.base.first_time": True}
            ))

    def test_negative_first_time_fails_closed(self):
        with self.assertRaises(KismetEventbusNewDeviceAdapterError):
            self._decode(envelope=self._envelope(
                **{"kismet.device.base.first_time": -1}
            ))

    def test_non_integer_first_time_fails_closed(self):
        for label, value in (("float", 1.5), ("string", "123"), ("list", [1])):
            with self.subTest(first_time_type=label):
                with self.assertRaises(KismetEventbusNewDeviceAdapterError):
                    self._decode(envelope=self._envelope(
                        **{"kismet.device.base.first_time": value}
                    ))

    # ------------------------------------------------------------------
    # 8. Contract-construction failure is translated to adapter error
    # ------------------------------------------------------------------

    def test_contract_construction_failure_translated(self):
        with self.assertRaises(KismetEventbusNewDeviceAdapterError):
            self._decode(hmac_key=b"")

    # ------------------------------------------------------------------
    # 9. Error messages expose no raw payload content
    # ------------------------------------------------------------------

    def test_error_messages_do_not_expose_raw_content(self):
        synthetic_mac = "DE:AD:BE:EF:00:01"
        synthetic_mac_padded = "  DE:AD:BE:EF:00:01  "
        synthetic_key = "synthetic-device-key-12345"
        synthetic_hmac = b"synthetic-hmac-material-here!!"
        synthetic_extra = "private-extra-field-value"

        payload = self._payload(
            **{
                "kismet.device.base.key": synthetic_key,
                "kismet.device.base.macaddr": synthetic_mac_padded,
                "kismet.device.base.first_time": -1,
                "extra_field": synthetic_extra,
            }
        )

        with self.assertRaises(
            KismetEventbusNewDeviceAdapterError
        ) as ctx:
            self._decode(
                envelope={NEW_DEVICE: payload},
                hmac_key=synthetic_hmac,
            )

        msg = str(ctx.exception)
        self.assertNotIn(synthetic_mac, msg)
        self.assertNotIn(synthetic_mac_padded, msg)
        self.assertNotIn(synthetic_key, msg)
        self.assertNotIn(synthetic_hmac.decode("ascii"), msg)
        self.assertNotIn(synthetic_extra, msg)

    # ------------------------------------------------------------------
    # 10. Static AST test: no forbidden imports
    # ------------------------------------------------------------------

    def test_no_forbidden_imports(self):
        forbidden_modules = (
            "observation_store",
            "kismet_eventbus_transport",
            "websocket",
            "socket",
            "pathlib",
            "sqlite3",
            "logging",
            "threading",
            "time",
            "flask",
            "socketio",
        )

        with open("kismet_eventbus_new_device_adapter.py") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for mod in forbidden_modules:
                        self.assertNotIn(
                            mod,
                            alias.name,
                            f"forbidden import '{alias.name}' "
                            f"contains '{mod}'",
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for mod in forbidden_modules:
                    self.assertNotIn(
                        mod,
                        module,
                        f"forbidden import from '{module}' "
                        f"contains '{mod}'",
                    )

    # ------------------------------------------------------------------
    # 11. Static AST test: no open/print/eval/exec calls
    # ------------------------------------------------------------------

    def test_no_forbidden_calls(self):
        forbidden_call_names = {"open", "print", "eval", "exec"}

        with open("kismet_eventbus_new_device_adapter.py") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    self.assertNotIn(
                        node.func.id,
                        forbidden_call_names,
                        f"forbidden call '{node.func.id}'",
                    )
                elif isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name):
                        full = f"{node.func.value.id}.{node.func.attr}"
                        self.assertNotIn(
                            "subprocess",
                            full,
                            f"forbidden call '{full}'",
                        )

    def test_no_subprocess_import(self):
        with open("kismet_eventbus_new_device_adapter.py") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(
                        alias.name,
                        "subprocess",
                        "forbidden import 'subprocess'",
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                self.assertNotEqual(
                    module,
                    "subprocess",
                    "forbidden import from 'subprocess'",
                )

    # ------------------------------------------------------------------
    # 12. Returned event is frozen
    # ------------------------------------------------------------------

    def test_returned_event_is_frozen(self):
        event = self._decode()
        with self.assertRaises(FrozenInstanceError):
            event.sensor_id = "mutated"


if __name__ == "__main__":
    unittest.main()
