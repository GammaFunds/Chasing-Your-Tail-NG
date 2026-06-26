"""Deterministic tests for KismetEventbusTransportConfigV1.

No real network, environment, file, or home-directory access is used.
"""

from __future__ import annotations

import ast
import builtins
import os
import unittest
from unittest.mock import patch

import kismet_eventbus_runtime_config as _config_module
from kismet_eventbus_runtime_config import (
    KismetEventbusTransportConfigError,
    KismetEventbusTransportConfigV1,
    create_kismet_eventbus_transport_config,
)

# ------------------------------------------------------------------
# Synthetic secret for testing — never a real credential.
# "Basic dGVzdDp0ZXN0" is "Basic test:test" in base64.
# ------------------------------------------------------------------

_SYNTHETIC_SECRET = b"Basic dGVzdDp0ZXN0"


def _valid_kwargs(**overrides: object) -> dict:
    kwargs: dict = {
        "base_url": "https://kismet.example.com",
        "topics": ("test-topic",),
        "authorization_header_value": _SYNTHETIC_SECRET,
        "tls_mode": "verify_required",
        "connect_timeout_s": 10.0,
        "reconnect_delay_s": 5.0,
        "stop_join_timeout_s": 5.0,
    }
    kwargs.update(overrides)
    return kwargs


class _MyStr(str):
    pass


class _MyTuple(tuple):
    pass


class _MyBytes(bytes):
    pass


class _MyInt(int):
    pass


class _MyFloat(float):
    pass


class KismetEventbusRuntimeConfigSurfaceTests(unittest.TestCase):
    """1. Public export surface."""

    def test_module_all_contains_exactly_two_names(self) -> None:
        self.assertEqual(
            sorted(_config_module.__all__),
            sorted(
                [
                    "KismetEventbusTransportConfigV1",
                    "create_kismet_eventbus_transport_config",
                ]
            ),
        )

    def test_error_class_missing_from_all(self) -> None:
        self.assertNotIn(
            "KismetEventbusTransportConfigError",
            _config_module.__all__,
        )

    def test_public_properties_present(self) -> None:
        for name in (
            "base_url",
            "topics",
            "tls_mode",
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
        ):
            self.assertTrue(
                hasattr(KismetEventbusTransportConfigV1, name),
                f"missing property {name}",
            )


class KismetEventbusRuntimeConfigImmutabilityTests(unittest.TestCase):
    """2. Immutability and identity semantics."""

    def test_config_has_no_instance_dict(self) -> None:
        config = create_kismet_eventbus_transport_config(**_valid_kwargs())
        self.assertFalse(hasattr(config, "__dict__"))

    def test_mutation_fails(self) -> None:
        config = create_kismet_eventbus_transport_config(**_valid_kwargs())
        with self.assertRaises(Exception):
            config._base_url = "https://evil.com"  # type: ignore[misc]

    def test_deletion_fails(self) -> None:
        config = create_kismet_eventbus_transport_config(**_valid_kwargs())
        with self.assertRaises(Exception):
            del config._base_url  # type: ignore[misc]

    def test_equal_content_not_structurally_equal(self) -> None:
        a = create_kismet_eventbus_transport_config(**_valid_kwargs())
        b = create_kismet_eventbus_transport_config(**_valid_kwargs())
        self.assertIsNot(a, b)
        self.assertFalse(a == b)
        self.assertIs(a.__eq__(b), NotImplemented)


class KismetEventbusRuntimeConfigReprStrTests(unittest.TestCase):
    """3. Secret not in repr or str."""

    def test_repr_does_not_contain_secret(self) -> None:
        config = create_kismet_eventbus_transport_config(**_valid_kwargs())
        r = repr(config)
        self.assertNotIn("dGVzdDp0ZXN0", r)
        self.assertNotIn(_SYNTHETIC_SECRET.decode("ascii"), r)
        self.assertNotIn(str(_SYNTHETIC_SECRET), r)
        self.assertIn("<redacted>", r)

    def test_str_does_not_contain_secret(self) -> None:
        config = create_kismet_eventbus_transport_config(**_valid_kwargs())
        s = str(config)
        self.assertNotIn("dGVzdDp0ZXN0", s)
        self.assertNotIn(_SYNTHETIC_SECRET.decode("ascii"), s)
        self.assertNotIn(str(_SYNTHETIC_SECRET), s)
        self.assertIn("<redacted>", s)

    def test_no_public_authorization_property(self) -> None:
        config = create_kismet_eventbus_transport_config(**_valid_kwargs())
        self.assertFalse(
            hasattr(config, "authorization_header_value")
        )

    def test_no_public_secret_name_in_dir(self) -> None:
        config = create_kismet_eventbus_transport_config(**_valid_kwargs())
        public_names = {name for name in dir(config) if not name.startswith("_")}
        for name in public_names:
            self.assertNotIn("authorization", name)
            self.assertNotIn("secret", name)


class KismetEventbusRuntimeConfigExactTypeTests(unittest.TestCase):
    """4. Exact type boundaries reject subclasses and wrong types."""

    def test_base_url_rejects_str_subclass(self) -> None:
        with self.assertRaises(KismetEventbusTransportConfigError):
            create_kismet_eventbus_transport_config(
                **_valid_kwargs(base_url=_MyStr("https://kismet.example.com"))
            )

    def test_base_url_rejects_non_string(self) -> None:
        for value in (123, None, b"https://kismet.example.com"):
            with self.subTest(value=value):
                with self.assertRaises(KismetEventbusTransportConfigError):
                    create_kismet_eventbus_transport_config(
                        **_valid_kwargs(base_url=value)
                    )

    def test_tls_mode_rejects_str_subclass(self) -> None:
        with self.assertRaises(KismetEventbusTransportConfigError):
            create_kismet_eventbus_transport_config(
                **_valid_kwargs(tls_mode=_MyStr("verify_required"))
            )

    def test_topics_rejects_tuple_subclass(self) -> None:
        with self.assertRaises(KismetEventbusTransportConfigError):
            create_kismet_eventbus_transport_config(
                **_valid_kwargs(topics=_MyTuple(["a"]))
            )

    def test_topics_rejects_non_tuple(self) -> None:
        for value in (["a"], {"a"}, "a", None):
            with self.subTest(value=value):
                with self.assertRaises(KismetEventbusTransportConfigError):
                    create_kismet_eventbus_transport_config(
                        **_valid_kwargs(topics=value)
                    )

    def test_topic_rejects_str_subclass(self) -> None:
        with self.assertRaises(KismetEventbusTransportConfigError):
            create_kismet_eventbus_transport_config(
                **_valid_kwargs(topics=(_MyStr("a"),))
            )

    def test_authorization_rejects_bytes_subclass(self) -> None:
        with self.assertRaises(KismetEventbusTransportConfigError):
            create_kismet_eventbus_transport_config(
                **_valid_kwargs(
                    authorization_header_value=_MyBytes(b"Basic dGVzdA==")
                )
            )

    def test_authorization_rejects_non_bytes(self) -> None:
        for value in (
            "Basic dGVzdA==",
            123,
            None,
            [b"Basic"],
        ):
            with self.subTest(value=value):
                with self.assertRaises(KismetEventbusTransportConfigError):
                    create_kismet_eventbus_transport_config(
                        **_valid_kwargs(authorization_header_value=value)
                    )

    def test_time_values_reject_int_subclass(self) -> None:
        for field in (
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
        ):
            with self.subTest(field=field):
                with self.assertRaises(KismetEventbusTransportConfigError):
                    create_kismet_eventbus_transport_config(
                        **_valid_kwargs(**{field: _MyInt(5)})
                    )

    def test_time_values_reject_float_subclass(self) -> None:
        for field in (
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
        ):
            with self.subTest(field=field):
                with self.assertRaises(KismetEventbusTransportConfigError):
                    create_kismet_eventbus_transport_config(
                        **_valid_kwargs(**{field: _MyFloat(5.0)})
                    )


class KismetEventbusRuntimeConfigUrlTests(unittest.TestCase):
    """5. Base URL matrix."""

    def _assert_valid(
        self,
        base_url: str,
        tls_mode: str = "verify_required",
        expected_base_url: str | None = None,
    ) -> None:
        config = create_kismet_eventbus_transport_config(
            base_url=base_url,
            topics=("t",),
            authorization_header_value=_SYNTHETIC_SECRET,
            tls_mode=tls_mode,
            connect_timeout_s=10,
            reconnect_delay_s=5,
            stop_join_timeout_s=5,
        )
        self.assertEqual(
            config.base_url,
            base_url
            if expected_base_url is None
            else expected_base_url,
        )

    def _assert_invalid(
        self, base_url: object, tls_mode: str = "verify_required"
    ) -> None:
        kwargs = _valid_kwargs(base_url=base_url, tls_mode=tls_mode)
        with self.assertRaises(KismetEventbusTransportConfigError):
            create_kismet_eventbus_transport_config(**kwargs)

    def test_remote_https(self) -> None:
        self._assert_valid("https://kismet.example.com")

    def test_remote_https_with_port(self) -> None:
        self._assert_valid("https://kismet.example.com:443")

    def test_remote_https_with_root_slash(self) -> None:
        self._assert_valid(
            "https://kismet.example.com/",
            expected_base_url="https://kismet.example.com",
        )

    def test_localhost_http(self) -> None:
        self._assert_valid(
            "http://localhost", tls_mode="loopback_plaintext"
        )

    def test_localhost_http_with_port(self) -> None:
        self._assert_valid(
            "http://localhost:8080", tls_mode="loopback_plaintext"
        )

    def test_non_exact_localhost_case_rejected(self) -> None:
        for value in (
            "http://LOCALHOST",
            "http://LOCALHOST:2501",
            "http://LocalHost",
            "http://LocalHost:2501",
            "http://localHOST",
            "http://localHOST:2501",
        ):
            with self.subTest(value=value):
                self._assert_invalid(
                    value,
                    tls_mode="loopback_plaintext",
                )

    def test_all_ascii_controls_and_space_rejected(self) -> None:
        code_points = tuple(range(0x21)) + (0x7F,)

        for code_point in code_points:
            value = (
                "https://kismet"
                f"{chr(code_point)}"
                ".example.com"
            )

            with self.subTest(code_point=code_point):
                self._assert_invalid(value)

    def test_parser_normalized_controls_rejected(self) -> None:
        cases = (
            (
                "https://kismet.example.com\n",
                "verify_required",
            ),
            (
                "https://kismet.\texample.com",
                "verify_required",
            ),
            (
                "http://local\nhost",
                "loopback_plaintext",
            ),
            (
                "http://127.0.0.\t1",
                "loopback_plaintext",
            ),
            (
                "http://[\r::1]",
                "loopback_plaintext",
            ),
        )

        for value, tls_mode in cases:
            with self.subTest(value=repr(value)):
                self._assert_invalid(
                    value,
                    tls_mode=tls_mode,
                )

    def test_ipv4_loopback_127_0_0_1(self) -> None:
        self._assert_valid(
            "http://127.0.0.1", tls_mode="loopback_plaintext"
        )

    def test_ipv4_loopback_subnet(self) -> None:
        self._assert_valid(
            "http://127.0.0.42", tls_mode="loopback_plaintext"
        )

    def test_ipv6_loopback(self) -> None:
        self._assert_valid(
            "http://[::1]", tls_mode="loopback_plaintext"
        )

    def test_ipv6_loopback_with_port(self) -> None:
        self._assert_valid(
            "http://[::1]:8080", tls_mode="loopback_plaintext"
        )

    def test_root_slash_canonicalization(self) -> None:
        cases = (
            (
                "https://kismet.example.com/",
                "verify_required",
                "https://kismet.example.com",
            ),
            (
                "http://localhost/",
                "loopback_plaintext",
                "http://localhost",
            ),
            (
                "http://[::1]:2501/",
                "loopback_plaintext",
                "http://[::1]:2501",
            ),
        )
        for raw, tls_mode, expected in cases:
            with self.subTest(raw=raw):
                self._assert_valid(
                    raw,
                    tls_mode=tls_mode,
                    expected_base_url=expected,
                )

    def test_remote_http_rejected(self) -> None:
        self._assert_invalid(
            "http://kismet.example.com", tls_mode="loopback_plaintext"
        )

    def test_credentials_rejected(self) -> None:
        self._assert_invalid("https://user:pass@kismet.example.com")
        self._assert_invalid("https://user@kismet.example.com")
        self._assert_invalid("https://:pass@kismet.example.com")

    def test_query_rejected(self) -> None:
        self._assert_invalid("https://kismet.example.com?q=1")

    def test_empty_query_markers_rejected(self) -> None:
        for value in (
            "https://kismet.example.com?",
            "https://kismet.example.com/?",
        ):
            with self.subTest(value=value):
                self._assert_invalid(value)

    def test_fragment_rejected(self) -> None:
        self._assert_invalid("https://kismet.example.com#frag")

    def test_empty_fragment_markers_rejected(self) -> None:
        for value in (
            "https://kismet.example.com#",
            "https://kismet.example.com/#",
        ):
            with self.subTest(value=value):
                self._assert_invalid(value)

    def test_path_rejected(self) -> None:
        self._assert_invalid("https://kismet.example.com/foo")
        self._assert_invalid("https://kismet.example.com/foo/")

    def test_semicolon_paths_rejected(self) -> None:
        for value in (
            "https://kismet.example.com/;",
            "https://kismet.example.com/;x",
            "https://kismet.example.com;x",
        ):
            with self.subTest(value=value):
                self._assert_invalid(value)

    def test_double_slash_path_rejected(self) -> None:
        self._assert_invalid("https://kismet.example.com//")

    def test_triple_slash_path_rejected(self) -> None:
        self._assert_invalid("https://kismet.example.com///")

    def test_port_zero_rejected(self) -> None:
        self._assert_invalid("https://kismet.example.com:0")

    def test_port_65536_rejected(self) -> None:
        self._assert_invalid("https://kismet.example.com:65536")

    def test_non_numeric_port_rejected(self) -> None:
        self._assert_invalid("https://kismet.example.com:abc")

    def test_empty_port_syntax_rejected(self) -> None:
        cases = (
            (
                "https://kismet.example.com:",
                "verify_required",
            ),
            (
                "https://kismet.example.com:/",
                "verify_required",
            ),
            (
                "http://localhost:",
                "loopback_plaintext",
            ),
            (
                "http://localhost:/",
                "loopback_plaintext",
            ),
            (
                "http://[::1]:",
                "loopback_plaintext",
            ),
            (
                "http://[::1]:/",
                "loopback_plaintext",
            ),
        )
        for value, tls_mode in cases:
            with self.subTest(value=value):
                self._assert_invalid(value, tls_mode=tls_mode)

    def test_missing_host_rejected(self) -> None:
        self._assert_invalid("https://")
        self._assert_invalid("http:///path")
        self._assert_invalid("https:///")

    def test_wrong_scheme_rejected(self) -> None:
        self._assert_invalid("ftp://kismet.example.com")
        self._assert_invalid("ws://kismet.example.com")
        self._assert_invalid("//kismet.example.com")

    def test_non_lowercase_schemes_rejected(self) -> None:
        cases = (
            ("HTTPS://kismet.example.com", "verify_required"),
            ("Https://kismet.example.com", "verify_required"),
            ("HTTP://localhost", "loopback_plaintext"),
            ("Http://localhost", "loopback_plaintext"),
        )
        for value, tls_mode in cases:
            with self.subTest(value=value):
                self._assert_invalid(value, tls_mode=tls_mode)

    def test_https_with_loopback_tls_rejected(self) -> None:
        self._assert_invalid(
            "https://kismet.example.com", tls_mode="loopback_plaintext"
        )

    def test_http_with_verify_required_rejected(self) -> None:
        self._assert_invalid(
            "http://localhost", tls_mode="verify_required"
        )

    def test_invalid_tls_mode_rejected(self) -> None:
        self._assert_invalid(
            "https://kismet.example.com", tls_mode="invalid"
        )

    def test_non_string_tls_mode_rejected(self) -> None:
        self._assert_invalid(
            "https://kismet.example.com", tls_mode=123  # type: ignore[arg-type]
        )


class KismetEventbusRuntimeConfigTopicsTests(unittest.TestCase):
    """6. Topic validation."""

    def test_stable_deduplication(self) -> None:
        config = create_kismet_eventbus_transport_config(
            **_valid_kwargs(topics=("a", "b", "a", "c", "b"))
        )
        self.assertEqual(config.topics, ("a", "b", "c"))

    def test_empty_tuple_rejected(self) -> None:
        with self.assertRaises(KismetEventbusTransportConfigError):
            create_kismet_eventbus_transport_config(
                **_valid_kwargs(topics=())
            )

    def test_empty_string_topic_rejected(self) -> None:
        with self.assertRaises(KismetEventbusTransportConfigError):
            create_kismet_eventbus_transport_config(
                **_valid_kwargs(topics=("valid", ""))
            )

    def test_leading_whitespace_rejected(self) -> None:
        with self.assertRaises(KismetEventbusTransportConfigError):
            create_kismet_eventbus_transport_config(
                **_valid_kwargs(topics=(" leading",))
            )

    def test_trailing_whitespace_rejected(self) -> None:
        with self.assertRaises(KismetEventbusTransportConfigError):
            create_kismet_eventbus_transport_config(
                **_valid_kwargs(topics=("trailing ",))
            )

    def test_both_whitespace_rejected(self) -> None:
        with self.assertRaises(KismetEventbusTransportConfigError):
            create_kismet_eventbus_transport_config(
                **_valid_kwargs(topics=(" both ",))
            )

    def test_non_tuple_rejected(self) -> None:
        for value in (["a"], {"a"}, "a", 123, None):
            with self.subTest(value=value):
                with self.assertRaises(KismetEventbusTransportConfigError):
                    create_kismet_eventbus_transport_config(
                        **_valid_kwargs(topics=value)
                    )

    def test_non_string_element_rejected(self) -> None:
        for value in (("a", 42), ("a", None), ("a", b"b")):
            with self.subTest(value=value):
                with self.assertRaises(KismetEventbusTransportConfigError):
                    create_kismet_eventbus_transport_config(
                        **_valid_kwargs(topics=value)
                    )

    def test_str_subclass_element_rejected(self) -> None:
        with self.assertRaises(KismetEventbusTransportConfigError):
            create_kismet_eventbus_transport_config(
                **_valid_kwargs(topics=(_MyStr("a"),))
            )

    def test_tuple_subclass_rejected(self) -> None:
        with self.assertRaises(KismetEventbusTransportConfigError):
            create_kismet_eventbus_transport_config(
                **_valid_kwargs(topics=_MyTuple(["a"]))
            )


class KismetEventbusRuntimeConfigAuthTests(unittest.TestCase):
    """7. Authorization header validation."""

    def _assert_secret_not_in_exception(self, value: object) -> None:
        secret_text = _SYNTHETIC_SECRET.decode("ascii")
        with self.assertRaises(KismetEventbusTransportConfigError) as ctx:
            create_kismet_eventbus_transport_config(
                **_valid_kwargs(authorization_header_value=value)
            )
        msg = str(ctx.exception)
        self.assertNotIn(secret_text, msg)
        self.assertNotIn("dGVzdDp0ZXN0", msg)
        self.assertNotIn("Basic", msg)

    def test_valid_bytes_accepted(self) -> None:
        config = create_kismet_eventbus_transport_config(
            **_valid_kwargs(authorization_header_value=b"Basic dGVzdA==")
        )
        self.assertIsInstance(config, KismetEventbusTransportConfigV1)

    def test_empty_rejected(self) -> None:
        self._assert_secret_not_in_exception(b"")

    def test_string_rejected(self) -> None:
        self._assert_secret_not_in_exception("Basic dGVzdA==")

    def test_bytes_subclass_rejected(self) -> None:
        self._assert_secret_not_in_exception(_MyBytes(b"Basic dGVzdA=="))

    def test_non_ascii_rejected(self) -> None:
        self._assert_secret_not_in_exception(b"\xff\xfe\x00")

    def test_cr_rejected(self) -> None:
        self._assert_secret_not_in_exception(b"Basic\rtest")

    def test_lf_rejected(self) -> None:
        self._assert_secret_not_in_exception(b"Basic\ntest")

    def test_crlf_rejected(self) -> None:
        self._assert_secret_not_in_exception(b"Basic\r\ntest")

    def test_invalid_auth_exception_has_no_value_bytes(self) -> None:
        invalid = b"\xff\xfe"
        with self.assertRaises(KismetEventbusTransportConfigError) as ctx:
            create_kismet_eventbus_transport_config(
                **_valid_kwargs(authorization_header_value=invalid)
            )
        msg = str(ctx.exception)
        self.assertNotIn("\xff", msg)
        self.assertNotIn("\xfe", msg)
        self.assertNotIn("xff", msg)
        self.assertNotIn("xfe", msg)


class KismetEventbusRuntimeConfigTimeTests(unittest.TestCase):
    """8. Time value validation matrix."""

    def _assert_rejected(self, field: str, value: object) -> None:
        with self.assertRaises(KismetEventbusTransportConfigError):
            create_kismet_eventbus_transport_config(
                **_valid_kwargs(**{field: value})
            )

    def _assert_accepted(self, field: str, value: object, expected: float) -> None:
        config = create_kismet_eventbus_transport_config(
            **_valid_kwargs(**{field: value})
        )
        self.assertEqual(getattr(config, field), expected)

    def test_valid_int_becomes_float(self) -> None:
        for field in (
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
        ):
            with self.subTest(field=field):
                self._assert_accepted(field, 5, 5.0)

    def test_valid_float_unchanged(self) -> None:
        config = create_kismet_eventbus_transport_config(
            **_valid_kwargs(
                connect_timeout_s=15.5,
                reconnect_delay_s=2.5,
                stop_join_timeout_s=3.5,
            )
        )
        self.assertEqual(config.connect_timeout_s, 15.5)
        self.assertEqual(config.reconnect_delay_s, 2.5)
        self.assertEqual(config.stop_join_timeout_s, 3.5)

    def test_true_rejected(self) -> None:
        for field in (
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
        ):
            with self.subTest(field=field):
                self._assert_rejected(field, True)

    def test_false_rejected(self) -> None:
        for field in (
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
        ):
            with self.subTest(field=field):
                self._assert_rejected(field, False)

    def test_none_rejected(self) -> None:
        for field in (
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
        ):
            with self.subTest(field=field):
                self._assert_rejected(field, None)

    def test_string_rejected(self) -> None:
        for field in (
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
        ):
            with self.subTest(field=field):
                self._assert_rejected(field, "10")

    def test_zero_rejected(self) -> None:
        for field in (
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
        ):
            with self.subTest(field=field):
                self._assert_rejected(field, 0)
                self._assert_rejected(field, 0.0)

    def test_negative_rejected(self) -> None:
        for field in (
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
        ):
            with self.subTest(field=field):
                self._assert_rejected(field, -1)
                self._assert_rejected(field, -1.0)

    def test_nan_rejected(self) -> None:
        for field in (
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
        ):
            with self.subTest(field=field):
                self._assert_rejected(field, float("nan"))

    def test_positive_inf_rejected(self) -> None:
        for field in (
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
        ):
            with self.subTest(field=field):
                self._assert_rejected(field, float("inf"))

    def test_negative_inf_rejected(self) -> None:
        for field in (
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
        ):
            with self.subTest(field=field):
                self._assert_rejected(field, float("-inf"))

    def test_int_subclass_rejected(self) -> None:
        for field in (
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
        ):
            with self.subTest(field=field):
                self._assert_rejected(field, _MyInt(5))

    def test_float_subclass_rejected(self) -> None:
        for field in (
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
        ):
            with self.subTest(field=field):
                self._assert_rejected(field, _MyFloat(5.0))


class KismetEventbusRuntimeConfigSideEffectTests(unittest.TestCase):
    """9. No environment, home, file, netrc, keyring, network, socket,
    or subprocess usage in the config module.
    """

    def test_no_forbidden_imports_anywhere_in_ast(self) -> None:
        forbidden = {
            "os",
            "pathlib",
            "netrc",
            "keyring",
            "keyczar",
            "cryptography",
            "socket",
            "subprocess",
        }

        with open("kismet_eventbus_runtime_config.py") as f:
            tree = ast.parse(f.read())

        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_roots.add(
                        alias.name.split(".")[0]
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_roots.add(
                        node.module.split(".")[0]
                    )

        found = imported_roots & forbidden
        self.assertEqual(
            found,
            set(),
            f"forbidden imports: {found}",
        )

    def test_no_discovery_or_io_calls_in_ast(self) -> None:
        forbidden_calls = {
            "open",
            "getenv",
            "environ",
            "expanduser",
            "netrc",
            "get_password",
            "socket",
            "Popen",
            "run",
            "call",
        }

        with open("kismet_eventbus_runtime_config.py") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    self.assertNotIn(
                        func.id,
                        forbidden_calls,
                        f"forbidden call {func.id}",
                    )
                elif isinstance(func, ast.Attribute):
                    self.assertNotIn(
                        func.attr,
                        forbidden_calls,
                        f"forbidden call .{func.attr}",
                    )

    def test_factory_performs_no_forbidden_io(self) -> None:
        def fail(name: str):
            def _fail(*args: object, **kwargs: object) -> object:
                raise AssertionError(f"forbidden {name} called")
            return _fail

        with patch.object(builtins, "open", fail("open")), \
             patch("os.environ.get", fail("os.environ.get")), \
             patch("os.path.expanduser", fail("expanduser")), \
             patch("netrc.netrc", fail("netrc.netrc")), \
             patch("keyring.get_password", fail("keyring.get_password")), \
             patch("socket.socket", fail("socket.socket")), \
             patch("subprocess.Popen", fail("subprocess.Popen")), \
             patch("subprocess.run", fail("subprocess.run")):
            config = create_kismet_eventbus_transport_config(**_valid_kwargs())
            self.assertIsInstance(config, KismetEventbusTransportConfigV1)


if __name__ == "__main__":
    unittest.main()
