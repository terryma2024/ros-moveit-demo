"""Gate 6 Batch 3: the Python encoder must reproduce the shared golden fixture.

RED: the production encoder does not exist yet, so this module fails to import the
symbol it must provide. It also locks the deterministic fixture: the frozen digest
must be exactly sha256(goal CDR), the permit UUID a fixed non-zero UUIDv4, and the
role the ARM enum value 1.
"""

import hashlib
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / ".." / "so101_mujoco_support" / "test" / "fixtures"
GOLDEN = (FIXTURES / "bound_frame_v2.bin").resolve()
MANIFEST = json.loads((FIXTURES / "bound_frame_v2.json").read_text())


def test_fixture_is_deterministic_and_self_consistent():
    frame = GOLDEN.read_bytes()
    assert len(frame) == MANIFEST["frame_len"] == 484
    assert hashlib.sha256(frame).hexdigest() == MANIFEST["frame_sha256"]
    # the frozen digest is exactly sha256 of the goal CDR carried by the frame
    goal_len = MANIFEST["goal_cdr_len"]
    goal_cdr = frame[-goal_len:]
    assert hashlib.sha256(goal_cdr).hexdigest() == MANIFEST["target_digest_hex"]
    assert MANIFEST["target_digest_hex"] == MANIFEST["goal_cdr_sha256"]
    # fixed, non-zero UUIDv4-shaped permit uuid and ARM == 1
    permit = bytes.fromhex(MANIFEST["permit_uuid_hex"])
    assert len(permit) == 16 and any(permit) and permit[6] >> 4 == 4
    assert MANIFEST["fields"]["role"] == 1
    assert MANIFEST["fields"]["claim_monotonic_ns"] <= MANIFEST["fields"]["deadline_ns"]


def test_production_encoder_reproduces_the_golden_bytes():
    from so101_demo.adapters.act.controller_reservation_client import _encode_bound_frame

    goal_cdr = GOLDEN.read_bytes()[-MANIFEST["goal_cdr_len"]:]
    encoded = _encode_bound_frame(
        generation=MANIFEST["fields"]["generation"], goal_uuid=bytes.fromhex(MANIFEST["goal_uuid_hex"]),
        role=MANIFEST["fields"]["role"], permit_uuid=bytes.fromhex(MANIFEST["permit_uuid_hex"]),
        target_digest=bytes.fromhex(MANIFEST["target_digest_hex"]),
        claim_monotonic_ns=MANIFEST["fields"]["claim_monotonic_ns"],
        deadline_ns=MANIFEST["fields"]["deadline_ns"],
        session_id=MANIFEST["fields"]["session_id"],
        broker_incarnation=MANIFEST["fields"]["broker_incarnation"],
        controller_incarnation=MANIFEST["fields"]["controller_incarnation"],
        controller_boot_incarnation=MANIFEST["fields"]["controller_boot_incarnation"],
        goal_cdr=goal_cdr, capability=b"\x5a" * 32)
    assert encoded == GOLDEN.read_bytes()


def test_the_codec_is_private_and_no_public_api_takes_authority_fields():
    from so101_demo.adapters import act

    client = act.controller_reservation_client
    assert not hasattr(client, "encode_bound_frame"), "the codec must stay private"
    import inspect

    public = {}
    for name, value in vars(client).items():
        if name.startswith("_") or not inspect.isfunction(value):
            continue
        public[name] = set(inspect.signature(value).parameters)
    forbidden = {"controller_incarnation", "controller_boot_incarnation", "claim_monotonic_ns",
                 "deadline_ns", "permit_uuid", "target_digest"}
    for name, parameters in public.items():
        assert not (parameters & forbidden), f"{name} exposes authority fields: {parameters}"
    assert "_encode_bound_frame" in vars(client)


def test_codec_negative_cases_are_all_rejected():
    import pytest as _pytest

    base = dict(generation=1, goal_uuid=bytes.fromhex(MANIFEST["goal_uuid_hex"]), role=1,
                permit_uuid=bytes.fromhex(MANIFEST["permit_uuid_hex"]),
                target_digest=bytes.fromhex(MANIFEST["target_digest_hex"]),
                claim_monotonic_ns=1, deadline_ns=2, session_id="s-1",
                broker_incarnation="b-1", controller_incarnation="inc-1",
                controller_boot_incarnation="boot-1", goal_cdr=b"\x00\x01",
                capability=b"\x5a" * 32)
    from so101_demo.adapters.act.controller_reservation_client import _encode_bound_frame

    _encode_bound_frame(**base)                                   # control: valid
    for overrides in ({"capability": None}, {"capability": b"\x5a" * 31},
                      {"capability": b"\x00" * 32}, {"generation": 0},
                      {"role": 0}, {"role": 4}, {"claim_monotonic_ns": 0},
                      {"deadline_ns": 0}, {"claim_monotonic_ns": 5, "deadline_ns": 4},
                      {"goal_uuid": b"\x00" * 16}, {"permit_uuid": b"\x00" * 16},
                      {"target_digest": b"\x00" * 32}, {"goal_cdr": b""},
                      {"session_id": ""}, {"session_id": "x" * 65},
                      {"session_id": "bad\x00name"}, {"session_id": "n\u00f6n-ascii"}):
        with _pytest.raises(ValueError):
            _encode_bound_frame(**{**base, **overrides})
