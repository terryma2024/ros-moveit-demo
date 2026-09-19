"""The Coordinator's local, one-time inference request registry.

Task 7 of the macOS MPS / private IPC plan. The v4 control channel carries no token, generation or
lease, so the *only* thing that stops a late, duplicate or foreign inference result from reaching
a robot action gate is this local registry. It therefore has to be exact:

* a `request_id` is opaque and never reused inside a campaign;
* registration atomically binds slot, point, attempt, model, input snapshot SHA, deadline and the
  current Broker's PID plus birth identity;
* a successful consume removes the binding immediately, so a second consume cannot succeed;
* cancel, timeout and consume share one lock boundary, so none of them can interleave;
* when the Broker identity changes, every binding to the old identity is invalidated at once, and
  a late result from the old Broker is refused rather than admitted.
"""

import threading
import time

import pytest

from so101_demo.parallel_batch.inference_registry import (
    CANCELLED,
    CONSUMED,
    EXPIRED,
    INVALIDATED,
    PENDING,
    InferenceBinding,
    InferenceRegistry,
    RegistryError,
    RegistryEvent,
)

BROKER_PID = 4242
BROKER_BIRTH = 777


def _registry(**kwargs):
    return InferenceRegistry(campaign_id="w2-campaign", **kwargs)


def _binding(registry, *, request_id="req-0001", slot="slot-0", point="p1", attempt=1,
             model="plastic-cup-yolo11n-seg-v1", sha256="a" * 64, deadline_s=30.0,
             broker_pid=BROKER_PID, broker_birth=BROKER_BIRTH):
    return registry.register_request(
        request_id=request_id, slot_id=slot, point_id=point, attempt=attempt, model_id=model,
        input_sha256=sha256,
        deadline_monotonic_ns=time.monotonic_ns() + int(deadline_s * 1_000_000_000),
        broker_pid=broker_pid, broker_birth_identity=broker_birth,
    )


# --------------------------------------------------------------------------------------
# registration
# --------------------------------------------------------------------------------------


def test_registration_binds_every_field_atomically():
    """One call records the whole binding; nothing is observable half-bound."""

    registry = _registry()
    binding = _binding(registry)
    assert isinstance(binding, InferenceBinding)
    assert binding.request_id == "req-0001"
    assert binding.slot_id == "slot-0"
    assert binding.point_id == "p1"
    assert binding.attempt == 1
    assert binding.model_id == "plastic-cup-yolo11n-seg-v1"
    assert binding.input_sha256 == "a" * 64
    assert binding.broker_pid == BROKER_PID
    assert binding.broker_birth_identity == BROKER_BIRTH
    assert binding.state == PENDING
    assert registry.pending() == (binding,)


def test_request_ids_are_opaque_and_never_reused_in_a_campaign():
    """A consumed id cannot be registered again, and a duplicate is refused outright."""

    registry = _registry()
    _binding(registry, request_id="req-0001")
    with pytest.raises(RegistryError, match="REQUEST_DUPLICATE"):
        _binding(registry, request_id="req-0001")
    registry.consume_result("req-0001", output_sha256="b" * 64)
    with pytest.raises(RegistryError, match="REQUEST_DUPLICATE"):
        _binding(registry, request_id="req-0001")


def test_registration_is_closed_against_bad_fields():
    """Every bound field is validated; a coerced or empty value is refused."""

    registry = _registry()
    base = dict(request_id="req-0002", slot_id="slot-0", point_id="p1", attempt=1,
                model_id="m", input_sha256="a" * 64,
                deadline_monotonic_ns=time.monotonic_ns() + 10**9,
                broker_pid=BROKER_PID, broker_birth_identity=BROKER_BIRTH)
    for mutated, reason in (
        ({"request_id": ""}, "REQUEST_ID"),
        ({"slot_id": ""}, "SLOT_ID"),
        ({"point_id": ""}, "POINT_ID"),
        ({"attempt": 0}, "ATTEMPT"),
        ({"attempt": True}, "ATTEMPT"),
        ({"model_id": ""}, "MODEL_ID"),
        ({"input_sha256": "short"}, "INPUT_SHA256"),
        ({"deadline_monotonic_ns": 0}, "DEADLINE"),
        ({"broker_pid": 0}, "BROKER_PID"),
        ({"broker_birth_identity": 0}, "BROKER_BIRTH_IDENTITY"),
    ):
        payload = dict(base)
        payload.update(mutated)
        with pytest.raises(RegistryError, match=reason):
            registry.register_request(**payload)


def test_a_second_campaign_is_a_separate_registry():
    """Campaign scoping is explicit, so ids from one campaign cannot consume in another."""

    first = InferenceRegistry(campaign_id="c-1")
    second = InferenceRegistry(campaign_id="c-2")
    _binding(first, request_id="req-0001")
    # The other campaign has never seen this id, so its decision is a refusal, not an admission.
    decision = second.consume_result("req-0001", output_sha256="b" * 64)
    assert decision.accepted is False
    assert decision.reason == "REQUEST_UNKNOWN"
    with pytest.raises(RegistryError, match="REQUEST_UNKNOWN"):
        second.cancel_request("req-0001", reason="cross-campaign")
    assert first.campaign_id == "c-1" and second.campaign_id == "c-2"
    assert [item.request_id for item in first.pending()] == ["req-0001"]


# --------------------------------------------------------------------------------------
# one-time consume
# --------------------------------------------------------------------------------------


def test_consume_succeeds_once_and_removes_the_binding():
    """A successful consume is the only path that admits a result, and it happens once."""

    registry = _registry()
    binding = _binding(registry)
    decision = registry.consume_result("req-0001", output_sha256="b" * 64)
    assert decision.accepted is True
    assert decision.reason == CONSUMED
    assert decision.binding is not None
    assert decision.binding.request_id == binding.request_id
    assert decision.binding.state == CONSUMED
    assert registry.pending() == ()
    assert registry.history()[-1].reason == CONSUMED

    second = registry.consume_result("req-0001", output_sha256="b" * 64)
    assert second.accepted is False
    assert second.reason == "REQUEST_ALREADY_CONSUMED"


def test_consume_rejects_an_unknown_request_id():
    """A result for a request that was never registered is refused, not admitted."""

    registry = _registry()
    decision = registry.consume_result("never-registered", output_sha256="b" * 64)
    assert decision.accepted is False
    assert decision.reason == "REQUEST_UNKNOWN"


def test_consume_rejects_an_input_snapshot_mismatch():
    """A result whose input SHA does not match the binding is refused and reported."""

    registry = _registry()
    _binding(registry, sha256="a" * 64)
    decision = registry.consume_result("req-0001", output_sha256="b" * 64,
                                       input_sha256="c" * 64)
    assert decision.accepted is False
    assert decision.reason == "SNAPSHOT_MISMATCH"
    assert registry.pending(), "a refused consume must not remove the binding"


def test_consume_rejects_a_result_from_an_old_broker_identity():
    """A result attributed to a different Broker birth identity is refused."""

    registry = _registry()
    _binding(registry)
    decision = registry.consume_result("req-0001", output_sha256="b" * 64,
                                       broker_pid=BROKER_PID,
                                       broker_birth_identity=BROKER_BIRTH + 1)
    assert decision.accepted is False
    assert decision.reason == "BROKER_IDENTITY_MISMATCH"


def test_consume_rejects_an_expired_deadline():
    """A result that arrives after its deadline is refused, and the binding is released."""

    registry = _registry()
    _binding(registry, deadline_s=-1.0)
    decision = registry.consume_result("req-0001", output_sha256="b" * 64)
    assert decision.accepted is False
    assert decision.reason == EXPIRED
    assert registry.pending() == ()
    assert registry.history()[-1].reason == EXPIRED


def test_consume_rejects_a_cancelled_request():
    """Cancel wins over a late result: the binding is gone and the consume is refused."""

    registry = _registry()
    _binding(registry)
    registry.cancel_request("req-0001", reason="worker stopped")
    decision = registry.consume_result("req-0001", output_sha256="b" * 64)
    assert decision.accepted is False
    assert decision.reason == "REQUEST_CANCELLED"
    assert registry.history()[-1].reason == CANCELLED


# --------------------------------------------------------------------------------------
# cancel, timeout, invalidation
# --------------------------------------------------------------------------------------


def test_cancel_is_idempotent_for_an_unknown_request_is_refused():
    """Cancelling twice is fine; cancelling something never registered is an error."""

    registry = _registry()
    _binding(registry)
    registry.cancel_request("req-0001", reason="first")
    registry.cancel_request("req-0001", reason="second")
    with pytest.raises(RegistryError, match="REQUEST_UNKNOWN"):
        registry.cancel_request("never-registered", reason="x")


def test_sweep_expired_releases_only_the_expired_bindings():
    """The timeout sweep is explicit and reports exactly what it released."""

    registry = _registry()
    _binding(registry, request_id="req-live", deadline_s=30.0)
    _binding(registry, request_id="req-dead", deadline_s=-1.0)
    released = registry.sweep_expired()
    assert [item.request_id for item in released] == ["req-dead"]
    assert [item.request_id for item in registry.pending()] == ["req-live"]
    assert [entry.reason for entry in registry.history()] == [EXPIRED]


def test_invalidate_broker_releases_every_binding_to_that_identity_once():
    """A Broker replacement invalidates all of its bindings in one call, and only once."""

    registry = _registry()
    _binding(registry, request_id="req-0001")
    _binding(registry, request_id="req-0002", slot="slot-1", point="p2")
    _binding(registry, request_id="req-0003", broker_pid=9999, broker_birth=8888)

    invalidated = registry.invalidate_broker(broker_pid=BROKER_PID,
                                             broker_birth_identity=BROKER_BIRTH)
    assert invalidated == ("req-0001", "req-0002")
    assert [item.request_id for item in registry.pending()] == ["req-0003"]
    assert registry.invalidate_broker(broker_pid=BROKER_PID,
                                      broker_birth_identity=BROKER_BIRTH) == ()

    # A late result from the replaced Broker is refused because the binding is gone.
    decision = registry.consume_result("req-0001", output_sha256="b" * 64)
    assert decision.accepted is False
    assert decision.reason in ("REQUEST_UNKNOWN", "REQUEST_INVALIDATED")
    assert INVALIDATED in [entry.reason for entry in registry.history()]


def test_history_is_append_only_and_carries_monotonic_timestamps():
    """Every decision is recorded in order, with a monotonic timestamp, for evidence."""

    registry = _registry()
    _binding(registry, request_id="req-0001")
    _binding(registry, request_id="req-0002", slot="slot-1", point="p2")
    registry.consume_result("req-0001", output_sha256="b" * 64)
    registry.cancel_request("req-0002", reason="worker stopped")
    history = registry.history()
    assert [entry.request_id for entry in history] == ["req-0001", "req-0002"]
    assert all(isinstance(entry, RegistryEvent) for entry in history)
    assert all(entry.monotonic_s > 0 for entry in history)
    stamps = [entry.monotonic_s for entry in history]
    assert stamps == sorted(stamps)


# --------------------------------------------------------------------------------------
# concurrency
# --------------------------------------------------------------------------------------


def test_concurrent_consumes_admit_exactly_one_result():
    """Eight racing consumes of one request produce exactly one acceptance."""

    registry = _registry()
    _binding(registry)
    accepted: list[bool] = []
    lock = threading.Lock()

    def racer(index: int) -> None:
        decision = registry.consume_result("req-0001", output_sha256=f"{index:064d}")
        with lock:
            accepted.append(decision.accepted)

    threads = [threading.Thread(target=racer, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert accepted.count(True) == 1, accepted
    assert accepted.count(False) == 7


def test_cancel_and_consume_racing_never_both_succeed():
    """Consume and cancel share one lock boundary, so at most one of them wins."""

    for _round in range(25):
        registry = _registry()
        _binding(registry)
        outcome: dict[str, bool] = {}
        barrier = threading.Barrier(2)

        def do_consume() -> None:
            barrier.wait(timeout=5)
            outcome["consume"] = registry.consume_result(
                "req-0001", output_sha256="b" * 64).accepted

        def do_cancel() -> None:
            barrier.wait(timeout=5)
            try:
                registry.cancel_request("req-0001", reason="race")
                outcome["cancel"] = True
            except RegistryError:
                outcome["cancel"] = False

        threads = [threading.Thread(target=do_consume), threading.Thread(target=do_cancel)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        assert outcome["consume"] != outcome["cancel"], outcome


def test_registry_is_bounded_by_the_configured_capacity():
    """A bounded registry refuses new registrations instead of growing without limit."""

    registry = _registry(capacity=2)
    _binding(registry, request_id="req-0001")
    _binding(registry, request_id="req-0002", slot="slot-1")
    with pytest.raises(RegistryError, match="REGISTRY_CAPACITY"):
        _binding(registry, request_id="req-0003", slot="slot-0")
    registry.consume_result("req-0001", output_sha256="b" * 64)
    _binding(registry, request_id="req-0003", slot="slot-0")


def test_no_token_generation_or_lease_is_ever_stored_or_required():
    """The v4 registry has no authentication field to check, by construction."""

    import dataclasses

    fields = {item.name for item in dataclasses.fields(InferenceBinding)}
    for retired in ("token", "generation", "lease", "lease_id", "endpoint_receipt"):
        assert retired not in fields
    registry = _registry()
    binding = _binding(registry)
    # Calling with a retired keyword is a plain TypeError: the API has no such parameter.
    with pytest.raises(TypeError):
        registry.register_request(
            request_id="req-x", slot_id="slot-0", point_id="p1", attempt=1, model_id="m",
            input_sha256="a" * 64, deadline_monotonic_ns=time.monotonic_ns() + 10**9,
            broker_pid=BROKER_PID, broker_birth_identity=BROKER_BIRTH, token="nope")
    assert binding.state == PENDING
