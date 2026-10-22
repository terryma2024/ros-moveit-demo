"""The Host's ownership of the policy service process, against a real child process that behaves like the service (or does not)."""

import json
import os
import signal
import sys
import textwrap
import time
from pathlib import Path

import pytest

import so101_demo
from so101_demo.runtime.act_rollout.policy_service import PolicyServiceError, PolicyServiceOwner, service_environment

BUNDLE, POLICY = "a" * 64, "b" * 64
PYTHONPATH = Path(so101_demo.__file__).parent.parent      # not resolved: a development shim is a symlink

FAKE_SERVICE = textwrap.dedent('''
    import argparse, json, os, signal, sys, time
    from pathlib import Path
    from so101_demo.runtime.act_policy.service import process_record

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="ok")
    parser.add_argument("--record-dir"); parser.add_argument("--socket"); parser.add_argument("--generation")
    args, _ = parser.parse_known_args()
    if args.mode == "exit_early":
        sys.exit(3)
    record_dir = Path(args.record_dir)
    record_dir.mkdir(mode=0o700)
    record = process_record()
    if args.mode == "bad_pid":
        record["pid"] = record["pid"] + 1
    (record_dir / "process-record.json").write_text(json.dumps({"kind": "ACT_POLICY_SERVICE_PROCESS", **record,
        "generation": args.generation}))
    stop = {"flag": False}
    if args.mode == "ignore_term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    else:
        signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    if args.mode == "never_ready":
        time.sleep(60)
    if args.mode == "partial_ready":
        (record_dir / "ready.json").write_text('{"ready": tr')     # a reader that polls must not take this for the record
        time.sleep(0.4)
    bundle = "%s" if args.mode != "wrong_bundle" else "f" * 64
    (record_dir / "ready.json.tmp").write_text(json.dumps({"ready": True, "service_generation": args.generation,
        "bundle_sha256": bundle, "policy_sha256": "%s", "cameras": ["head", "wrist"], "state_dim": 8,
        "image_shape": [4, 6, 3], "socket": args.socket, "pid": os.getpid()}))
    os.replace(record_dir / "ready.json.tmp", record_dir / "ready.json")
    while not stop["flag"]:
        time.sleep(0.02)
    (record_dir / "stop-proof.json").write_text(json.dumps({"terminated": args.mode != "unclean", "pid": os.getpid()}))
''' % (BUNDLE, POLICY))


def owner(tmp_path, mode="ok", **changes):
    script = tmp_path / "fake_service.py"
    script.write_text(FAKE_SERVICE)
    run = tmp_path / "run"
    (run / "ipc").mkdir(parents=True, exist_ok=True)
    (run / "services").mkdir(exist_ok=True)
    arguments = dict(run=run, python=Path(sys.executable), pythonpath=PYTHONPATH, bundle_dir=tmp_path / "bundle",
                     gpu_uuid="GPU-00000000-0000-0000-0000-000000000000", generation="gen-1",
                     expected={"bundle_sha256": BUNDLE, "policy_sha256": POLICY, "cameras": ["head", "wrist"], "state_dim": 8,
                               "image_shape": [4, 6, 3]},
                     command=[sys.executable, str(script), "--mode", mode], start_timeout_s=20.0, stop_timeout_s=5.0)
    arguments.update(changes)
    return PolicyServiceOwner(**arguments)


def test_the_service_starts_is_proved_to_be_the_started_process_and_stops_with_its_proof(tmp_path):
    served = owner(tmp_path)
    ready = served.start()
    try:
        assert ready["ready"] is True and served.record["pid"] == served.process.pid
        assert served.healthy() is True
        launch = json.loads((served.home / "launch.json").read_text())
        assert launch["argv"][-1] == "head,wrist" and "--record-dir" in launch["argv"] and "--gpu-uuid" in launch["argv"]
        assert launch["environment"]["CUDA_VISIBLE_DEVICES"].startswith("GPU-") and launch["environment"]["PYTHONNOUSERSITE"] == "1"
        assert "ROS_DOMAIN_ID" not in launch["environment"] and "LD_LIBRARY_PATH" not in launch["environment"]
        assert (served.home / "host-start.json").is_file() and (served.socket_dir.stat().st_mode & 0o777) == 0o700
    finally:
        result = served.stop()
    assert result["confirmed"] is True and result["exit_code"] == 0 and result["forced"] is False and result["errors"] == []
    assert result["stop_proof"]["terminated"] is True and len(result["stop_proof_sha256"]) == 64
    assert served.healthy() is False
    assert served.stop() is result                                # idempotent
    assert json.loads((served.home / "host-stop.json").read_text())["confirmed"] is True


def test_a_service_that_exits_before_it_is_ready_is_a_start_failure(tmp_path):
    served = owner(tmp_path, mode="exit_early")
    with pytest.raises(PolicyServiceError, match="POLICY_SERVICE_EXITED_BEFORE_READY: 3"):
        served.start()
    stopped = served.stop()                              # it is gone: stopped; the start failure is the run's fault
    assert stopped["confirmed"] is True and stopped["start_failed"] is True and stopped["exit_code"] == 3


def test_a_service_that_is_never_ready_is_killed_at_the_start_timeout(tmp_path):
    served = owner(tmp_path, mode="never_ready", start_timeout_s=1.0)
    with pytest.raises(PolicyServiceError, match="POLICY_SERVICE_READY_TIMEOUT"):
        served.start()
    assert served.process.poll() is not None
    assert served.stop()["confirmed"] is True and served.stop_result["start_failed"] is True


def test_a_service_for_another_bundle_is_refused_and_killed(tmp_path):
    served = owner(tmp_path, mode="wrong_bundle")
    with pytest.raises(PolicyServiceError, match="POLICY_SERVICE_BUNDLE_MISMATCH"):
        served.start()
    assert served.process.poll() is not None


def test_a_process_record_that_is_not_the_started_process_is_refused_and_killed(tmp_path):
    served = owner(tmp_path, mode="bad_pid")
    with pytest.raises(PolicyServiceError, match="POLICY_SERVICE_IDENTITY_MISMATCH"):
        served.start()
    assert served.process.poll() is not None


def test_a_service_that_ignores_sigterm_is_killed_and_the_stop_is_not_confirmed(tmp_path):
    served = owner(tmp_path, mode="ignore_term", stop_timeout_s=0.5)
    served.start()
    result = served.stop()
    assert result["confirmed"] is False and result["forced"] is True
    assert "POLICY_SERVICE_STOP_TIMEOUT" in result["errors"] and served.process.poll() is not None


def test_a_stop_proof_that_says_not_terminated_is_not_a_confirmed_stop(tmp_path):
    served = owner(tmp_path, mode="unclean")
    served.start()
    result = served.stop()
    assert result["confirmed"] is False and "POLICY_SERVICE_STOP_PROOF_UNCONFIRMED" in result["errors"]


def test_health_needs_a_live_process_the_proved_identity_and_the_probe(tmp_path):
    answers = {"value": True}
    served = owner(tmp_path, health_probe=lambda: answers["value"])
    assert served.healthy() is False                              # not started
    served.start()
    try:
        assert served.healthy() is True
        answers["value"] = False
        assert served.healthy() is False
        answers["value"] = True
        served.record["start_ticks"] += 1                          # a process that is no longer the one that was proved
        assert served.healthy() is False
    finally:
        served.record["start_ticks"] -= 1
        served.stop()


def test_a_stop_after_a_crash_reports_the_missing_proof(tmp_path):
    served = owner(tmp_path)
    served.start()
    os.kill(served.process.pid, signal.SIGKILL)
    served.process.wait(5)
    result = served.stop()
    assert result["confirmed"] is False and "POLICY_SERVICE_STOP_PROOF_MISSING" in result["errors"]
    assert any(error.startswith("POLICY_SERVICE_EXIT_CODE") for error in result["errors"])


def test_the_service_directory_and_socket_are_never_reused(tmp_path):
    first = owner(tmp_path)
    first.prepare()
    (first.socket_dir / "policy.sock").write_text("stale")
    with pytest.raises(PolicyServiceError, match="POLICY_SERVICE_DIRECTORY_NOT_NEW"):
        first.start()


def test_the_environment_is_a_minimal_allowlist(tmp_path):
    environment = service_environment(pythonpath=PYTHONPATH, gpu_uuid="GPU-x", tmp=tmp_path,
                                      base={"PATH": "/bin", "HOME": "/h", "ROS_DOMAIN_ID": "181", "LD_LIBRARY_PATH": "/ros",
                                            "PYTHONPATH": "/gate", "SECRET": "x"})
    assert set(environment) == {"PATH", "HOME", "PYTHONPATH", "CUDA_VISIBLE_DEVICES", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE",
                                "TMPDIR", "TMP", "TEMP"}
    assert environment["PYTHONPATH"] == str(PYTHONPATH) and environment["CUDA_VISIBLE_DEVICES"] == "GPU-x"


def test_a_ready_record_that_is_read_half_written_is_read_again_until_it_parses(tmp_path):
    served = owner(tmp_path, mode="partial_ready")
    ready = served.start()
    try:
        assert ready["ready"] is True and served.healthy() is True
    finally:
        served.stop()


def test_an_interrupt_during_the_start_ends_the_start_kills_the_child_and_the_stop_is_judged_after(tmp_path):
    import threading

    served = owner(tmp_path, mode="never_ready", start_timeout_s=30.0)
    outcome = {}

    def start():
        try:
            served.start()
        except PolicyServiceError as error:
            outcome["error"] = str(error)
    thread = threading.Thread(target=start)
    thread.start()
    for _ in range(500):
        if served.process is not None:
            break
        time.sleep(0.01)
    result = served.stop()                              # what an interrupted run does
    thread.join(10)
    assert not thread.is_alive() and "POLICY_SERVICE_START_ABORTED" in outcome["error"]
    assert served.process.poll() is not None and result["confirmed"] is True and result["start_failed"] is True
    with pytest.raises(PolicyServiceError, match="POLICY_SERVICE_START_ABORTED"):
        served.start()                                  # a stopped owner starts nothing


def test_a_stop_before_any_start_is_trivially_confirmed_and_a_later_start_is_refused(tmp_path):
    served = owner(tmp_path)
    assert served.stop() == {"confirmed": True, "started": False, "errors": []}
    with pytest.raises(PolicyServiceError, match="POLICY_SERVICE_START_ABORTED"):
        served.start()


def test_the_first_reason_a_service_is_unhealthy_is_kept(tmp_path):
    answers = iter(["POLICY_SERVICE_FAULT: x", "OTHER"])
    served = owner(tmp_path, health_probe=lambda: next(answers))
    served.start()
    try:
        assert served.healthy() is False and served.unhealthy_reason == "POLICY_SERVICE_FAULT: x"
        assert served.healthy() is False and served.unhealthy_reason == "POLICY_SERVICE_FAULT: x"
    finally:
        served.stop()


class HealthClient:
    def __init__(self, *replies):
        self.replies = list(replies)

    def query(self, kind, timeout_s):
        assert kind == "policy_health_query"
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


def health(available=True, consecutive_errors=0, reason=""):
    return {"available": available, "consecutive_errors": consecutive_errors, "reason": reason}


def test_the_service_health_probe_stops_a_faulted_service_that_is_still_alive():
    from so101_demo.runtime.act_rollout.policy_service import service_health_probe

    probe = service_health_probe(HealthClient(health(), health(available=False, reason="POLICY_MODEL_FAILED: RuntimeError")))
    assert probe() is True
    assert probe() == "POLICY_SERVICE_FAULT: POLICY_MODEL_FAILED: RuntimeError"


def test_the_service_health_probe_stops_on_a_run_of_error_replies_but_not_on_refusals_for_load():
    from so101_demo.runtime.act_rollout.policy_service import service_health_probe

    probe = service_health_probe(HealthClient(health(consecutive_errors=2), health(consecutive_errors=3)), max_consecutive_errors=3)
    assert probe() is True
    assert probe() == "POLICY_SERVICE_ERRORS: 3 replies in a row were errors"


def test_the_service_health_probe_tolerates_one_unanswered_query_but_not_three_in_a_row():
    from so101_demo.runtime.act_rollout.policy_service import service_health_probe

    slow = TimeoutError("late")
    probe = service_health_probe(HealthClient(slow, health(), slow, slow, slow), max_unanswered=3)
    assert probe() is True and probe() is True                       # one unanswered, then answered: the count starts again
    assert probe() is True and probe() is True
    assert probe().startswith("HEALTH_QUERY_UNANSWERED: 3 in a row")
