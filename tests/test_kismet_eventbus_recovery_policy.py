"""Deterministic tests for KismetEventbusRecoveryPolicyV1."""

from __future__ import annotations

import inspect
import threading
import time
import unittest
from unittest.mock import (
    PropertyMock,
    patch,
)

import kismet_eventbus_recovery_policy as policy_module
from kismet_eventbus_recovery_policy import (
    KismetEventbusRecoveryPolicyError,
    KismetEventbusRecoveryPolicyResultV1,
    KismetEventbusRecoveryPolicyV1,
)
from kismet_eventbus_runtime import (
    KismetEventbusRuntime,
    KismetEventbusRuntimeError,
    KismetEventbusRuntimeHealthV1,
    KismetEventbusRuntimeStatusV1,
)
from kismet_eventbus_runtime_config import (
    create_kismet_eventbus_transport_config,
)
from kismet_eventbus_transport import KismetEventbusTransportStatusV1

import kismet_eventbus_runtime as runtime_module


_SYNTHETIC_AUTH = b"Basic c3ludGhldGljOnRlc3Q="
_SYNTHETIC_HMAC = b"runtime-test-hmac-key-32-bytes!!"
_SYNTHETIC_PATH = "synthetic/runtime-observations.sqlite"
_SYNTHETIC_SESSION = "session_runtime_test"
_SYNTHETIC_SENSOR = "sensor_runtime_test"


def _config():
    return create_kismet_eventbus_transport_config(
        base_url="https://kismet.example.test",
        topics=("NEW_DEVICE",),
        authorization_header_value=_SYNTHETIC_AUTH,
        tls_mode="verify_required",
        connect_timeout_s=10.0,
        reconnect_delay_s=5.0,
        stop_join_timeout_s=1.0,
    )


_ONE_PROVIDER = lambda: 1


class _RecordingTransport:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.start_error: BaseException | None = None
        self.stop_error: BaseException | None = None
        self._status = KismetEventbusTransportStatusV1(
            worker_lifecycle="stopped",
            stop_requested=False,
        )

    @property
    def status(self) -> KismetEventbusTransportStatusV1:
        return self._status

    def set_status(
        self,
        worker_lifecycle: str,
        *,
        stop_requested: bool = False,
    ) -> None:
        self._status = KismetEventbusTransportStatusV1(
            worker_lifecycle=worker_lifecycle,
            stop_requested=stop_requested,
        )

    def start(self) -> None:
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error
        self.set_status("running")

    def stop(self) -> None:
        self.stop_calls += 1
        if self.stop_error is not None:
            raise self.stop_error
        self.set_status("stopped")


class _BlockingStartTransport(_RecordingTransport):
    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def start(self) -> None:
        self.start_calls += 1
        self.entered.set()
        self.release.wait()


def _make_runtime(transport: _RecordingTransport) -> KismetEventbusRuntime:
    with patch.object(
        runtime_module.KismetEventbusTransport,
        "from_config",
        return_value=transport,
    ):
        return KismetEventbusRuntime(
            _config(),
            _SYNTHETIC_PATH,
            hmac_key=_SYNTHETIC_HMAC,
            collection_session_id=_SYNTHETIC_SESSION,
            sensor_id=_SYNTHETIC_SENSOR,
            ingest_timestamp_us_provider=_ONE_PROVIDER,
        )


# ======================================================================
# Public surface
# ======================================================================


class TestPublicSurface(unittest.TestCase):
    def test_exact_all(self) -> None:
        self.assertEqual(
            policy_module.__all__,
            (
                "KismetEventbusRecoveryPolicyError",
                "KismetEventbusRecoveryPolicyResultV1",
                "KismetEventbusRecoveryPolicyV1",
            ),
        )

    def test_error_is_runtime_error(self) -> None:
        self.assertTrue(issubclass(KismetEventbusRecoveryPolicyError, RuntimeError))
        self.assertIs(type(KismetEventbusRecoveryPolicyError.__bases__[0]), type)

    def test_error_instantiation(self) -> None:
        exc = KismetEventbusRecoveryPolicyError("test")
        self.assertIsInstance(exc, KismetEventbusRecoveryPolicyError)
        self.assertIsInstance(exc, RuntimeError)

    def test_result_dataclass_fields(self) -> None:
        fields = tuple(KismetEventbusRecoveryPolicyResultV1.__dataclass_fields__)
        self.assertEqual(
            fields,
            (
                "outcome",
                "attempts_in_window",
                "pre_call_health",
                "post_call_health",
            ),
        )

    def test_result_is_frozen_slotted_no_repr_no_eq(self) -> None:
        self.assertTrue(
            KismetEventbusRecoveryPolicyResultV1.__dataclass_params__.frozen
        )
        self.assertTrue(
            KismetEventbusRecoveryPolicyResultV1.__dataclass_params__.slots
        )
        self.assertFalse(
            KismetEventbusRecoveryPolicyResultV1.__dataclass_params__.repr
        )
        self.assertFalse(
            KismetEventbusRecoveryPolicyResultV1.__dataclass_params__.eq
        )

    def test_policy_init_signature(self) -> None:
        sig = inspect.signature(KismetEventbusRecoveryPolicyV1.__init__)
        params = list(sig.parameters)
        self.assertEqual(
            params,
            ["self", "max_attempts", "cooldown_after_budget_s", "monotonic_time_provider"],
        )
        self.assertEqual(
            sig.parameters["max_attempts"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )
        self.assertEqual(
            sig.parameters["cooldown_after_budget_s"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )
        self.assertEqual(
            sig.parameters["monotonic_time_provider"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )
        self.assertIsNot(
            sig.parameters["monotonic_time_provider"].default,
            inspect.Parameter.empty,
        )

    def test_apply_signature(self) -> None:
        sig = inspect.signature(KismetEventbusRecoveryPolicyV1.apply)
        params = list(sig.parameters)
        self.assertEqual(params, ["self", "runtime"])
        self.assertEqual(
            sig.parameters["runtime"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )


# ======================================================================
# Constructor validation
# ======================================================================


class TestConstructorValidation(unittest.TestCase):
    def test_max_attempts_rejects_non_int(self) -> None:
        for value in (None, "3", 3.0, [3], {3}):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    KismetEventbusRecoveryPolicyV1(
                        max_attempts=value,  # type: ignore[arg-type]
                        cooldown_after_budget_s=10.0,
                    )

    def test_max_attempts_rejects_bool(self) -> None:
        with self.assertRaises(TypeError):
            KismetEventbusRecoveryPolicyV1(
                max_attempts=True,  # type: ignore[arg-type]
                cooldown_after_budget_s=10.0,
            )

    def test_max_attempts_rejects_int_subclass(self) -> None:
        class MyInt(int):
            pass

        with self.assertRaises(TypeError):
            KismetEventbusRecoveryPolicyV1(
                max_attempts=MyInt(3),
                cooldown_after_budget_s=10.0,
            )

    def test_max_attempts_must_be_positive(self) -> None:
        for value in (0, -1, -100):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    KismetEventbusRecoveryPolicyV1(
                        max_attempts=value,
                        cooldown_after_budget_s=10.0,
                    )

    def test_cooldown_rejects_non_float(self) -> None:
        for value in (None, "10", 10, [10.0], {10.0}):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    KismetEventbusRecoveryPolicyV1(
                        max_attempts=3,
                        cooldown_after_budget_s=value,  # type: ignore[arg-type]
                    )

    def test_cooldown_rejects_bool(self) -> None:
        with self.assertRaises(TypeError):
            KismetEventbusRecoveryPolicyV1(
                max_attempts=3,
                cooldown_after_budget_s=True,  # type: ignore[arg-type]
            )

    def test_cooldown_rejects_float_subclass(self) -> None:
        class MyFloat(float):
            pass

        with self.assertRaises(TypeError):
            KismetEventbusRecoveryPolicyV1(
                max_attempts=3,
                cooldown_after_budget_s=MyFloat(10.0),
            )

    def test_cooldown_rejects_non_positive(self) -> None:
        for value in (0.0, -1.0, -0.1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    KismetEventbusRecoveryPolicyV1(
                        max_attempts=3,
                        cooldown_after_budget_s=value,
                    )

    def test_cooldown_rejects_non_finite(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    KismetEventbusRecoveryPolicyV1(
                        max_attempts=3,
                        cooldown_after_budget_s=value,
                    )

    def test_monotonic_time_provider_rejects_non_callable(self) -> None:
        for value in (None, "not_callable", 42, [time.monotonic]):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    KismetEventbusRecoveryPolicyV1(
                        max_attempts=3,
                        cooldown_after_budget_s=10.0,
                        monotonic_time_provider=value,  # type: ignore[arg-type]
                    )

    def test_constructor_errors_are_content_free(self) -> None:
        with self.assertRaises(TypeError) as ctx:
            KismetEventbusRecoveryPolicyV1(
                max_attempts="bad",  # type: ignore[arg-type]
                cooldown_after_budget_s=10.0,
            )
        self.assertNotIn("bad", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            KismetEventbusRecoveryPolicyV1(
                max_attempts=0,
                cooldown_after_budget_s=10.0,
            )
        self.assertNotIn("credential", str(ctx.exception))
        self.assertNotIn("secret", str(ctx.exception))

    def test_construction_does_not_invoke_time_provider(self) -> None:
        calls: list[float] = []

        def provider() -> float:
            calls.append(time.monotonic())
            return 100.0

        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=provider,
        )
        self.assertEqual(calls, [])

    def test_construction_performs_no_side_effects(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
        )
        self.assertEqual(policy._attempts_in_window, 0)
        self.assertIsNone(policy._blocked_until_s)
        self.assertIsNone(policy._last_sampled_time_s)


# ======================================================================
# Runtime type rejection
# ======================================================================


class TestRuntimeTypeRejection(unittest.TestCase):
    def test_rejects_non_runtime_object(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
        )
        with self.assertRaises(TypeError):
            policy.apply(runtime=object())  # type: ignore[arg-type]

    def test_rejects_runtime_subclass(self) -> None:
        class FakeRuntime(KismetEventbusRuntime):
            pass

        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
        )
        with self.assertRaises(TypeError):
            policy.apply(runtime=FakeRuntime)  # type: ignore[arg-type]

    def test_rejects_string(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
        )
        with self.assertRaises(TypeError):
            policy.apply(runtime="not_a_runtime")  # type: ignore[arg-type]

    def test_rejects_none(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
        )
        with self.assertRaises(TypeError):
            policy.apply(runtime=None)  # type: ignore[arg-type]


# ======================================================================
# Concurrency
# ======================================================================


class TestConcurrency(unittest.TestCase):
    def test_concurrent_apply_raises_error(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
        )
        transport = _BlockingStartTransport()
        runtime = _make_runtime(transport)

        errors: list[BaseException] = []

        def concurrent_apply() -> None:
            try:
                with self.assertRaises(KismetEventbusRecoveryPolicyError) as ctx:
                    with patch.object(
                        KismetEventbusRuntime,
                        "health",
                        new_callable=PropertyMock,
                        return_value=KismetEventbusRuntimeHealthV1(
                            runtime_lifecycle="start_failed",
                            transport_worker_lifecycle="stopped",
                            control_state="recovery_required",
                            recovery_action="start",
                        ),
                    ):
                        policy.apply(runtime=runtime)
                self.assertEqual(
                    str(ctx.exception),
                    "recovery policy transition in progress",
                )
            except BaseException as exc:
                errors.append(exc)

        self.assertTrue(policy._lock.acquire(blocking=False))

        thread = threading.Thread(target=concurrent_apply)
        thread.start()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())

        policy._lock.release()

        self.assertEqual(errors, [])

    def test_lock_available_after_concurrent_rejection(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        self.assertTrue(policy._lock.acquire(blocking=False))
        with self.assertRaises(KismetEventbusRecoveryPolicyError):
            policy.apply(runtime=runtime)
        policy._lock.release()

        self.assertTrue(policy._lock.acquire(blocking=False))
        policy._lock.release()

    def test_lock_released_on_type_error(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
        )
        with self.assertRaises(TypeError):
            policy.apply(runtime=object())  # type: ignore[arg-type]

        self.assertTrue(policy._lock.acquire(blocking=False))
        policy._lock.release()


# ======================================================================
# No-op (recovery_action == "none")
# ======================================================================


class TestNoOp(unittest.TestCase):
    def test_noop_returns_not_required(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="stopped",
                transport_worker_lifecycle="stopped",
                control_state="inactive",
                recovery_action="none",
            ),
        ):
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "not_required")
        self.assertEqual(result.attempts_in_window, 0)
        self.assertIs(result.pre_call_health, result.post_call_health)

    def test_noop_resets_window_state(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        policy._attempts_in_window = 5
        policy._blocked_until_s = 999.0

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="active",
                transport_worker_lifecycle="running",
                control_state="worker_running",
                recovery_action="none",
            ),
        ):
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "not_required")
        self.assertEqual(result.attempts_in_window, 0)
        self.assertEqual(policy._attempts_in_window, 0)
        self.assertIsNone(policy._blocked_until_s)

    def test_noop_does_not_call_clock(self) -> None:
        def fail_provider() -> float:
            raise AssertionError("clock should not be called")

        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=fail_provider,
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="stopped",
                transport_worker_lifecycle="stopped",
                control_state="inactive",
                recovery_action="none",
            ),
        ):
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "not_required")


# ======================================================================
# Wait / transition deferred
# ======================================================================


class TestWaitTransition(unittest.TestCase):
    def test_wait_returns_transition_deferred(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="starting",
                transport_worker_lifecycle="stopped",
                control_state="transitioning",
                recovery_action="wait",
            ),
        ):
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "transition_deferred")
        self.assertIsNone(result.post_call_health)

    def test_wait_does_not_mutate_state(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        policy._attempts_in_window = 2
        policy._blocked_until_s = 500.0

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="stopping",
                transport_worker_lifecycle="running",
                control_state="transitioning",
                recovery_action="wait",
            ),
        ):
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "transition_deferred")
        self.assertEqual(result.attempts_in_window, 2)
        self.assertEqual(policy._attempts_in_window, 2)
        self.assertEqual(policy._blocked_until_s, 500.0)

    def test_wait_does_not_call_clock(self) -> None:
        def fail_provider() -> float:
            raise AssertionError("clock should not be called")

        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=fail_provider,
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="starting",
                transport_worker_lifecycle="stopped",
                control_state="transitioning",
                recovery_action="wait",
            ),
        ):
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "transition_deferred")


# ======================================================================
# Clock validation
# ======================================================================


class TestClockValidation(unittest.TestCase):
    def test_accepts_exact_int_result(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=lambda: 100,
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ), patch.object(
            KismetEventbusRuntime,
            "recover",
        ) as mock_recover:
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "recover_invoked")
        mock_recover.assert_called_once()

    def test_accepts_exact_float_result(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=lambda: 100.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ), patch.object(
            KismetEventbusRuntime,
            "recover",
        ) as mock_recover:
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "recover_invoked")
        mock_recover.assert_called_once()

    def test_rejects_bool(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=lambda: True,  # type: ignore[return-value]
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ):
            with self.assertRaises(TypeError):
                policy.apply(runtime=runtime)

    def test_rejects_int_subclass(self) -> None:
        class MyInt(int):
            pass

        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=lambda: MyInt(100),
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ):
            with self.assertRaises(TypeError):
                policy.apply(runtime=runtime)

    def test_rejects_float_subclass(self) -> None:
        class MyFloat(float):
            pass

        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=lambda: MyFloat(100.0),
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ):
            with self.assertRaises(TypeError):
                policy.apply(runtime=runtime)

    def test_rejects_nan(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=lambda: float("nan"),
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ):
            with self.assertRaises(ValueError):
                policy.apply(runtime=runtime)

    def test_rejects_positive_infinity(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=lambda: float("inf"),
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ):
            with self.assertRaises(ValueError):
                policy.apply(runtime=runtime)

    def test_rejects_negative_infinity(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=lambda: float("-inf"),
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ):
            with self.assertRaises(ValueError):
                policy.apply(runtime=runtime)

    def test_rejects_negative(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=lambda: -1.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ):
            with self.assertRaises(ValueError):
                policy.apply(runtime=runtime)

    def test_rejects_regressed_time(self) -> None:
        calls = [200.0, 100.0]

        def provider() -> float:
            return calls.pop(0)

        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=provider,
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ), patch.object(KismetEventbusRuntime, "recover"):
            policy.apply(runtime=runtime)

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ):
            with self.assertRaises(KismetEventbusRecoveryPolicyError) as ctx:
                policy.apply(runtime=runtime)

        self.assertEqual(str(ctx.exception), "monotonic time regressed")

    def test_rejected_clock_does_not_mutate_state(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        policy._last_sampled_time_s = 50.0
        policy._attempts_in_window = 1

        def bad_provider() -> float:
            return -1.0

        policy._monotonic_time_provider = bad_provider

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ):
            with self.assertRaises(ValueError):
                policy.apply(runtime=runtime)

        self.assertEqual(policy._attempts_in_window, 1)
        self.assertEqual(policy._last_sampled_time_s, 50.0)

    def test_clock_called_exactly_once_on_eligible_path(self) -> None:
        call_count = 0

        def provider() -> float:
            nonlocal call_count
            call_count += 1
            return 100.0

        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=provider,
        )
        runtime = _make_runtime(_RecordingTransport())

        self.assertEqual(call_count, 0)

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ), patch.object(KismetEventbusRuntime, "recover"):
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "recover_invoked")
        self.assertEqual(call_count, 1)

    def test_provider_exception_propagates_unchanged(self) -> None:
        exc = RuntimeError("original provider error")

        def provider() -> float:
            raise exc

        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=provider,
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                policy.apply(runtime=runtime)

        self.assertIs(ctx.exception, exc)


# ======================================================================
# Budget and cooldown
# ======================================================================


class TestBudgetAndCooldown(unittest.TestCase):
    def test_first_through_nth_attempt_invocation(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=60.0,
            monotonic_time_provider=lambda: 100.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        for i in range(1, 4):
            with self.subTest(attempt=i):
                with patch.object(
                    KismetEventbusRuntime,
                    "health",
                    new_callable=PropertyMock,
                    return_value=KismetEventbusRuntimeHealthV1(
                        runtime_lifecycle="start_failed",
                        transport_worker_lifecycle="stopped",
                        control_state="recovery_required",
                        recovery_action="start",
                    ),
                ), patch.object(
                    KismetEventbusRuntime,
                    "recover",
                ), patch.object(
                    KismetEventbusRuntime,
                    "health",
                    new_callable=PropertyMock,
                    return_value=KismetEventbusRuntimeHealthV1(
                        runtime_lifecycle="start_failed",
                        transport_worker_lifecycle="stopped",
                        control_state="recovery_required",
                        recovery_action="start",
                    ),
                ) as mock_health:
                    mock_health.return_value = KismetEventbusRuntimeHealthV1(
                        runtime_lifecycle="start_failed",
                        transport_worker_lifecycle="stopped",
                        control_state="recovery_required",
                        recovery_action="start",
                    )
                    result = policy.apply(runtime=runtime)

                self.assertEqual(result.outcome, "recover_invoked")
                self.assertEqual(result.attempts_in_window, i)

        self.assertEqual(policy._attempts_in_window, 3)

    def test_cooldown_begins_on_nth_attempt(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=60.0,
            monotonic_time_provider=lambda: 100.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        for i in range(1, 4):
            with patch.object(
                KismetEventbusRuntime,
                "health",
                new_callable=PropertyMock,
                return_value=KismetEventbusRuntimeHealthV1(
                    runtime_lifecycle="start_failed",
                    transport_worker_lifecycle="stopped",
                    control_state="recovery_required",
                    recovery_action="start",
                ),
            ), patch.object(KismetEventbusRuntime, "recover"):
                result = policy.apply(runtime=runtime)
            self.assertEqual(result.outcome, "recover_invoked")

        self.assertIsNotNone(policy._blocked_until_s)
        self.assertAlmostEqual(policy._blocked_until_s, 160.0)

    def test_cooldown_returns_budget_cooldown(self) -> None:
        now = [100.0]

        def provider() -> float:
            return now[0]

        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=60.0,
            monotonic_time_provider=provider,
        )
        runtime = _make_runtime(_RecordingTransport())

        for _ in range(3):
            with patch.object(
                KismetEventbusRuntime,
                "health",
                new_callable=PropertyMock,
                return_value=KismetEventbusRuntimeHealthV1(
                    runtime_lifecycle="start_failed",
                    transport_worker_lifecycle="stopped",
                    control_state="recovery_required",
                    recovery_action="start",
                ),
            ), patch.object(KismetEventbusRuntime, "recover"):
                policy.apply(runtime=runtime)

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ):
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "budget_cooldown")
        self.assertEqual(result.attempts_in_window, 3)
        self.assertIsNone(result.post_call_health)

    def test_budget_cooldown_does_not_mutate_state(self) -> None:
        now = [100.0]

        def provider() -> float:
            return now[0]

        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=60.0,
            monotonic_time_provider=provider,
        )
        runtime = _make_runtime(_RecordingTransport())

        for _ in range(3):
            with patch.object(
                KismetEventbusRuntime,
                "health",
                new_callable=PropertyMock,
                return_value=KismetEventbusRuntimeHealthV1(
                    runtime_lifecycle="start_failed",
                    transport_worker_lifecycle="stopped",
                    control_state="recovery_required",
                    recovery_action="start",
                ),
            ), patch.object(KismetEventbusRuntime, "recover"):
                policy.apply(runtime=runtime)

        self.assertEqual(policy._attempts_in_window, 3)
        self.assertAlmostEqual(policy._blocked_until_s, 160.0)

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ):
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "budget_cooldown")
        self.assertEqual(policy._attempts_in_window, 3)
        self.assertAlmostEqual(policy._blocked_until_s, 160.0)

    def test_cooldown_budget_resets_exact_boundary(self) -> None:
        now = [100.0]

        def provider() -> float:
            return now[0]

        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=60.0,
            monotonic_time_provider=provider,
        )
        runtime = _make_runtime(_RecordingTransport())

        for _ in range(3):
            with patch.object(
                KismetEventbusRuntime,
                "health",
                new_callable=PropertyMock,
                return_value=KismetEventbusRuntimeHealthV1(
                    runtime_lifecycle="start_failed",
                    transport_worker_lifecycle="stopped",
                    control_state="recovery_required",
                    recovery_action="start",
                ),
            ), patch.object(KismetEventbusRuntime, "recover"):
                policy.apply(runtime=runtime)

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ):
            result = policy.apply(runtime=runtime)
        self.assertEqual(result.outcome, "budget_cooldown")

        now[0] = 160.0

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ), patch.object(KismetEventbusRuntime, "recover"):
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "recover_invoked")
        self.assertEqual(result.attempts_in_window, 1)
        self.assertEqual(policy._attempts_in_window, 1)


# ======================================================================
# Recover exception propagation
# ======================================================================


class TestRecoverExceptions(unittest.TestCase):
    def test_recover_exception_propagates_unchanged(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=lambda: 100.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        exc = RuntimeError("original recover error")

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ), patch.object(
            KismetEventbusRuntime,
            "recover",
            side_effect=exc,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                policy.apply(runtime=runtime)

        self.assertIs(ctx.exception, exc)

    def test_exceptions_count_as_attempts(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=2,
            cooldown_after_budget_s=60.0,
            monotonic_time_provider=lambda: 100.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        exc = RuntimeError("recover failed")

        for i in range(1, 3):
            with self.subTest(attempt=i):
                with patch.object(
                    KismetEventbusRuntime,
                    "health",
                    new_callable=PropertyMock,
                    return_value=KismetEventbusRuntimeHealthV1(
                        runtime_lifecycle="start_failed",
                        transport_worker_lifecycle="stopped",
                        control_state="recovery_required",
                        recovery_action="start",
                    ),
                ), patch.object(
                    KismetEventbusRuntime,
                    "recover",
                    side_effect=exc,
                ):
                    with self.assertRaises(RuntimeError):
                        policy.apply(runtime=runtime)

        self.assertEqual(policy._attempts_in_window, 2)
        self.assertIsNotNone(policy._blocked_until_s)

    def test_transition_in_progress_from_recover_counts_as_attempt(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=1,
            cooldown_after_budget_s=60.0,
            monotonic_time_provider=lambda: 100.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
            return_value=KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="start_failed",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="start",
            ),
        ), patch.object(
            KismetEventbusRuntime,
            "recover",
            side_effect=KismetEventbusRuntimeError("transition_in_progress"),
        ):
            with self.assertRaises(KismetEventbusRuntimeError):
                policy.apply(runtime=runtime)

        self.assertEqual(policy._attempts_in_window, 1)
        self.assertIsNotNone(policy._blocked_until_s)


# ======================================================================
# Health reset after recover
# ======================================================================


class TestHealthResetAfterRecover(unittest.TestCase):
    def test_post_recover_health_none_resets_window(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=60.0,
            monotonic_time_provider=lambda: 100.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        policy._attempts_in_window = 2

        pre_health = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="start_failed",
            transport_worker_lifecycle="stopped",
            control_state="recovery_required",
            recovery_action="start",
        )
        post_health = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="active",
            transport_worker_lifecycle="running",
            control_state="worker_running",
            recovery_action="none",
        )

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
        ) as mock_health, patch.object(
            KismetEventbusRuntime,
            "recover",
        ):
            mock_health.side_effect = [pre_health, post_health]
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "recover_invoked")
        self.assertEqual(policy._attempts_in_window, 0)
        self.assertIsNone(policy._blocked_until_s)

    def test_post_recover_health_not_none_retains_state(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=60.0,
            monotonic_time_provider=lambda: 100.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        policy._attempts_in_window = 1

        pre_health = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="start_failed",
            transport_worker_lifecycle="stopped",
            control_state="recovery_required",
            recovery_action="start",
        )

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
        ) as mock_health, patch.object(
            KismetEventbusRuntime,
            "recover",
        ):
            mock_health.side_effect = [pre_health, pre_health]
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "recover_invoked")
        self.assertEqual(policy._attempts_in_window, 2)


# ======================================================================
# Pre/post health snapshot access
# ======================================================================


class TestHealthSnapshotAccess(unittest.TestCase):
    def test_health_read_exactly_once_for_non_recover_paths(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        health_reads: list[object] = []
        health_value = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="stopped",
            transport_worker_lifecycle="stopped",
            control_state="inactive",
            recovery_action="none",
        )

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
        ) as mock_health:
            def track_health(*args: object, **kwargs: object) -> KismetEventbusRuntimeHealthV1:
                health_reads.append(None)
                return health_value
            mock_health.side_effect = track_health

            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "not_required")
        self.assertEqual(len(health_reads), 1)

    def test_health_read_twice_for_recover_path(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=lambda: 100.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        health_reads: list[object] = []

        pre = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="start_failed",
            transport_worker_lifecycle="stopped",
            control_state="recovery_required",
            recovery_action="start",
        )
        post = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="active",
            transport_worker_lifecycle="running",
            control_state="worker_running",
            recovery_action="none",
        )

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
        ) as mock_health, patch.object(
            KismetEventbusRuntime,
            "recover",
        ):
            mock_health.side_effect = [pre, post]
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "recover_invoked")
        self.assertIs(result.pre_call_health, pre)
        self.assertIs(result.post_call_health, post)


# ======================================================================
# No authoritative claim
# ======================================================================


class TestNoAuthoritativeClaim(unittest.TestCase):
    def test_result_does_not_contain_executed_action(self) -> None:
        policy = KismetEventbusRecoveryPolicyV1(
            max_attempts=3,
            cooldown_after_budget_s=10.0,
            monotonic_time_provider=lambda: 100.0,
        )
        runtime = _make_runtime(_RecordingTransport())

        pre = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="start_failed",
            transport_worker_lifecycle="stopped",
            control_state="recovery_required",
            recovery_action="start",
        )
        post = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="active",
            transport_worker_lifecycle="running",
            control_state="worker_running",
            recovery_action="none",
        )

        with patch.object(
            KismetEventbusRuntime,
            "health",
            new_callable=PropertyMock,
        ) as mock_health, patch.object(
            KismetEventbusRuntime,
            "recover",
        ):
            mock_health.side_effect = [pre, post]
            result = policy.apply(runtime=runtime)

        self.assertEqual(result.outcome, "recover_invoked")
        self.assertFalse(hasattr(result, "action"))
        self.assertFalse(hasattr(result, "executed_action"))
        self.assertFalse(hasattr(result, "recovery_action"))


# ======================================================================
# repr and str
# ======================================================================


class TestReprStr(unittest.TestCase):
    def test_content_free_repr_and_str(self) -> None:
        health = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="stopped",
            transport_worker_lifecycle="stopped",
            control_state="inactive",
            recovery_action="none",
        )
        result = KismetEventbusRecoveryPolicyResultV1(
            outcome="not_required",
            attempts_in_window=0,
            pre_call_health=health,
            post_call_health=health,
        )

        expected = "KismetEventbusRecoveryPolicyResultV1()"
        self.assertEqual(repr(result), expected)
        self.assertEqual(str(result), expected)

    def test_repr_str_contains_no_field_values(self) -> None:
        health = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="stopped",
            transport_worker_lifecycle="stopped",
            control_state="inactive",
            recovery_action="none",
        )
        result = KismetEventbusRecoveryPolicyResultV1(
            outcome="not_required",
            attempts_in_window=42,
            pre_call_health=health,
            post_call_health=health,
        )

        output = f"{result!r} {result!s}"
        self.assertNotIn("not_required", output)
        self.assertNotIn("42", output)
        self.assertNotIn("stopped", output)
        self.assertNotIn("inactive", output)


# ======================================================================
# Network and side-effect freedom
# ======================================================================


class TestNoForbiddenSideEffects(unittest.TestCase):
    def test_no_forbidden_imports_in_module(self) -> None:
        import ast

        with open(policy_module.__file__) as f:
            tree = ast.parse(f.read())

        forbidden_imports = {
            "logging",
            "os",
            "socket",
            "sqlite3",
            "subprocess",
            "webbrowser",
            "ssl",
            "websocket",
        }

        imported: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(
                    alias.name.split(".")[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])

        imported.discard("threading")
        overlap = imported & forbidden_imports
        self.assertFalse(
            overlap,
            f"Forbidden imports: {overlap}",
        )


# ======================================================================
# Result validation
# ======================================================================


class TestResultValidation(unittest.TestCase):
    def test_valid_outcomes_accepted(self) -> None:
        health = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="stopped",
            transport_worker_lifecycle="stopped",
            control_state="inactive",
            recovery_action="none",
        )

        for outcome in ("not_required", "transition_deferred", "budget_cooldown", "recover_invoked"):
            with self.subTest(outcome=outcome):
                result = KismetEventbusRecoveryPolicyResultV1(
                    outcome=outcome,
                    attempts_in_window=0,
                    pre_call_health=health,
                    post_call_health=(
                        health if outcome in ("not_required", "recover_invoked") else None
                    ),
                )
                self.assertEqual(result.outcome, outcome)

    def test_invalid_outcome_rejected(self) -> None:
        health = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="stopped",
            transport_worker_lifecycle="stopped",
            control_state="inactive",
            recovery_action="none",
        )

        with self.assertRaises(ValueError):
            KismetEventbusRecoveryPolicyResultV1(
                outcome="invalid",
                attempts_in_window=0,
                pre_call_health=health,
                post_call_health=None,
            )

    def test_negative_attempts_rejected(self) -> None:
        health = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="stopped",
            transport_worker_lifecycle="stopped",
            control_state="inactive",
            recovery_action="none",
        )

        with self.assertRaises(ValueError):
            KismetEventbusRecoveryPolicyResultV1(
                outcome="not_required",
                attempts_in_window=-1,
                pre_call_health=health,
                post_call_health=health,
            )

    def test_invalid_pre_call_health_type_rejected(self) -> None:
        with self.assertRaises(ValueError):
            KismetEventbusRecoveryPolicyResultV1(
                outcome="not_required",
                attempts_in_window=0,
                pre_call_health="not_health",  # type: ignore[arg-type]
                post_call_health=None,
            )

    def test_invalid_post_call_health_type_rejected(self) -> None:
        health = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="stopped",
            transport_worker_lifecycle="stopped",
            control_state="inactive",
            recovery_action="none",
        )

        with self.assertRaises(ValueError):
            KismetEventbusRecoveryPolicyResultV1(
                outcome="recover_invoked",
                attempts_in_window=0,
                pre_call_health=health,
                post_call_health="not_health",  # type: ignore[arg-type]
            )

    def test_frozen_result_cannot_be_modified(self) -> None:
        health = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="stopped",
            transport_worker_lifecycle="stopped",
            control_state="inactive",
            recovery_action="none",
        )
        result = KismetEventbusRecoveryPolicyResultV1(
            outcome="not_required",
            attempts_in_window=0,
            pre_call_health=health,
            post_call_health=health,
        )

        with self.assertRaises(Exception):
            result.outcome = "recover_invoked"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
