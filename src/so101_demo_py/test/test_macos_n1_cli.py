"""The two public W1 entry points and the one-shot guard handover across `exec`.

Task 7 of the macOS service campaign closure plan. A W1 entry names exactly one profile: there is
no `--batch-kind` switch to flip, and one entry never runs the other profile's document. The guard
phase is a fresh observation every time - an existing `start-guard.json`, whatever it says and
whoever wrote it, is audit material only - and the admission that crosses the `exec` into the
broker phase travels through one inherited pipe created by this process, is consumed exactly once,
and is checked against the scope, the owner birth identity, the epoch and its age.
"""

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.cli import macos_n1_first_pass, macos_n1_retry
from so101_demo.cli.macos_w2_campaign import (
    GUARD_RESULT_FD_VARIABLE,
    campaign_guard_scope,
    broker_phase_guard,
    run_guard_phase,
)
from so101_demo.parallel_batch.accelerator_probe import AcceleratorSnapshot
from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_v6
from so101_demo.parallel_batch.start_guard import FAIL, PASS, StartGuardPolicy
from so101_demo.parallel_batch.start_guard_probe import (
    CAMPAIGN_GUARD_EPOCH,
    GuardHandoverRefused,
    consume_guard_handover,
    guard_handover_document,
    publish_guard_handover,
    run_campaign_start_guard,
)

PACKAGE = Path(__file__).resolve().parents[1]
V4_CONFIG = PACKAGE / "config/mujoco/parallel_batch_v4_macos_mps_w2.yaml"
V5_CONFIG = PACKAGE / "config/mujoco/parallel_batch_v5_macos_mps_w1_retry.yaml"
V6_CONFIG = PACKAGE / "config/mujoco/parallel_batch_v6_macos_mps_w1_first_pass.yaml"

MPS_POLICY = StartGuardPolicy(mps_minimum_headroom_bytes=1 << 30)


def _healthy():
    return AcceleratorSnapshot(
        kind="mps", selector="default", available_bytes=8 << 30,
        recommended_max_memory_bytes=16 << 30, current_allocated_memory_bytes=0,
        driver_allocated_memory_bytes=0,
        metric_source="unified-memory-proxy:vm_stat+torch.mps")


def _refusing(**_: object):
    from so101_demo.parallel_batch.accelerator_probe import ProbeError

    raise ProbeError("MPS_UNAVAILABLE", "torch.backends.mps.is_available() is false")


def _state_root(tmp_path):
    """The probe coordination root the guard needs; the tests never touch the task root."""

    return Path(tmp_path) / "start-guard-state"


def _entry_argv(module, config, tmp_path, *, points=("p1",), extra=()):
    evidence = tmp_path / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    return [
        str(module.__name__),
        "--config", str(config),
        "--campaign-id", "b-n1",
        "--batch-id", "batch-n1",
        "--evidence-root", str(evidence),
        "--yolo-weights", str(tmp_path / "yolo.pt"),
        "--grounded-root", str(tmp_path / "grounded"),
        *extra,
    ] + [item for point in points for item in ("--point-id", point)]


# --------------------------------------------------------------------------------------
# one entry, one profile, no generic batch-kind switch
# --------------------------------------------------------------------------------------


def test_each_public_entry_names_exactly_one_profile():
    """The routing key is fixed by the entry point, not by a flag."""

    assert macos_n1_retry.EXECUTION_PROFILE == "MPS_W1_FULL_RESTART_RETRY"
    assert macos_n1_retry.BATCH_KIND == "FULL_RESTART_RETRY"
    assert macos_n1_first_pass.EXECUTION_PROFILE == "MPS_W1_FIRST_PASS"
    assert macos_n1_first_pass.BATCH_KIND == "FIRST_PASS"

    for module in (macos_n1_retry, macos_n1_first_pass):
        accepted = {option for action in module.build_parser()._actions
                    for option in action.option_strings}
        assert "--batch-kind" not in accepted
        assert "--execution-profile" not in accepted
        assert "--worker-count" not in accepted, "the worker count is the profile's, not a knob"
        with pytest.raises(SystemExit):
            module.build_parser().parse_args(["--batch-kind", "FIRST_PASS"])


def test_the_retry_entry_refuses_a_first_pass_document(tmp_path):
    """No cross-profile reuse: v6 through the retry entry is a refusal, not a fallback."""

    argv = _entry_argv(macos_n1_retry, V6_CONFIG, tmp_path, extra=["--skip-models"])
    assert macos_n1_retry.run(argv[1:]) == 1


def test_the_first_pass_entry_refuses_a_retry_document(tmp_path):
    """And the other way round."""

    argv = _entry_argv(macos_n1_first_pass, V5_CONFIG, tmp_path, extra=["--skip-models"])
    assert macos_n1_first_pass.run(argv[1:]) == 1


def test_each_entry_refuses_a_w2_document(tmp_path):
    """A v4 exact-W2 document is not a W1 request."""

    for module in (macos_n1_retry, macos_n1_first_pass):
        argv = _entry_argv(module, V4_CONFIG, tmp_path / module.__name__, extra=["--skip-models"])
        assert module.run(argv[1:]) == 1


@pytest.mark.skipif(sys.platform != "darwin", reason="the MPS CLI route requires macOS")
def test_each_entry_composes_exactly_one_slot_without_models(tmp_path, capsys):
    """`--skip-models` proves the route and the plan, and is never a pass."""

    argv = _entry_argv(macos_n1_first_pass, V6_CONFIG, tmp_path, points=("p1", "p2"),
                       extra=["--skip-models"])
    assert macos_n1_first_pass.run(argv[1:]) == 3
    document = json.loads(capsys.readouterr().out)

    assert document["status"] == "COMPOSED_ONLY"
    assert document["plan"]["execution_profile"] == "MPS_W1_FIRST_PASS"
    assert document["plan"]["batch_kind"] == "FIRST_PASS"
    assert document["plan"]["worker_count"] == 1
    assert document["plan"]["slots"]["slot_ids"] == ["slot-0"]
    assert document["plan"]["ros_domain_ids"] == [181]
    assert document["plan"]["selected_point_ids"] == ["p1", "p2"]


def test_the_w1_lease_names_the_profile_the_worker_executes(tmp_path, capsys):
    """The Worker's own lease - and therefore its evidence - names the approved profile.

    A Worker that only knew "I am a Worker" would make the profile a property of whoever spawned it;
    the lease carries it, and the Worker copies it into its result document.
    """

    import json as _json

    from so101_demo.cli.macos_w2_campaign import build_worker_leases
    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_v6
    from so101_demo.parallel_batch.queue import DurablePointQueue
    from so101_demo.parallel_batch.selection import build_first_pass_selection
    from so101_demo.parallel_batch.w1_composition import compose_w1_first_pass

    point_ids = ("task_start", "cup_test_forward_5cm", "cup_test_left_5cm",
                 "cup_test_right_5cm")
    catalog = tmp_path / "moveit_expert_validation_points_v1.yaml"
    catalog.write_bytes(
        (PACKAGE / "config/mujoco/moveit_expert_validation_points_v1.yaml").read_bytes())
    binding = build_first_pass_selection(
        catalog_path=catalog, point_ids=point_ids, campaign_id="b-n1", batch_id="b-n1",
        config_sha256="c" * 64, runtime_closure_sha256="d" * 64)
    queue = DurablePointQueue(root=tmp_path / "queue", binding=binding)
    plan = compose_w1_first_pass(config=load_parallel_runtime_config_v6(V6_CONFIG),
                                 config_path=V6_CONFIG, campaign_id="b-n1", batch_id="b-n1",
                                 selected_point_ids=point_ids, evidence_root=tmp_path)
    leases = build_worker_leases(plan=plan, batch_id="b-n1", evidence_root=tmp_path,
                                 input_sha256="a" * 64, binding=binding, queue=queue)

    assert list(leases) == ["w1"]
    document = _json.loads(Path(leases["w1"]["lease_path"]).read_text())
    assert document["execution_profile"] == "MPS_W1_FIRST_PASS"
    assert document["batch_kind"] == "FIRST_PASS"
    assert document["schema_version"] == 6
    assert document["slot_id"] == "slot-0"

    # The Worker child is a script (`sys.argv` drives it), so the check that it records the
    # identity it was handed is made against its source rather than by importing it.
    worker_source = (PACKAGE / "src/cli/macos_w2_worker.py").read_text()
    for name in ("execution_profile", "batch_kind", "schema_version"):
        assert name in worker_source, "the Worker must record the profile it executed"


@pytest.mark.skipif(sys.platform != "darwin", reason="the MPS CLI route requires macOS")
def test_the_retry_entry_keeps_the_full_restart_batch_kind(tmp_path, capsys):
    """The retry entry composes the retry route, with one slot and one domain."""

    argv = _entry_argv(macos_n1_retry, V5_CONFIG, tmp_path, extra=["--skip-models"])
    assert macos_n1_retry.run(argv[1:]) == 3
    document = json.loads(capsys.readouterr().out)
    assert document["plan"]["execution_profile"] == "MPS_W1_FULL_RESTART_RETRY"
    assert document["plan"]["batch_kind"] == "FULL_RESTART_RETRY"
    assert document["plan"]["worker_count"] == 1


# --------------------------------------------------------------------------------------
# a fresh guard phase, never the on-disk verdict
# --------------------------------------------------------------------------------------


def test_the_campaign_guard_is_a_fresh_observation_even_when_a_verdict_exists(tmp_path):
    """A `start-guard.json` with a PASS verdict cannot admit a start by itself."""

    arguments = SimpleNamespace(evidence_root=tmp_path)
    verdict = tmp_path / "start-guard.json"
    verdict.write_text(json.dumps({"status": "PASS", "epoch": 7, "owner_pid": 1}))

    document, result = run_guard_phase(
        arguments, policy=MPS_POLICY, batch_id="b-n1", worker_count=1, probe=_refusing,
        state_root=_state_root(tmp_path))

    assert result.status == FAIL
    assert result.checks["mps_accelerator"].reason == "MPS_UNAVAILABLE"
    assert document["status"] == FAIL
    # the audit copy is refreshed from the fresh observation, never copied from the old file
    on_disk = json.loads(verdict.read_text())
    assert on_disk["status"] == FAIL and on_disk["epoch"] == CAMPAIGN_GUARD_EPOCH
    assert on_disk["scope"]["owner_pid"] == os.getpid()


def test_a_stale_fail_verdict_does_not_block_a_healthy_fresh_probe(tmp_path):
    """The file is audit material: a FAIL from an old epoch must not decide this start."""

    arguments = SimpleNamespace(evidence_root=tmp_path)
    (tmp_path / "start-guard.json").write_text(
        json.dumps({"status": "FAIL", "epoch": 3, "reason": "MPS_HEADROOM_BELOW_MINIMUM"}))

    _, result = run_guard_phase(
        arguments, policy=MPS_POLICY, batch_id="b-n1", worker_count=1,
        probe=lambda **_: _healthy(), state_root=_state_root(tmp_path))

    assert result.status in (PASS, "WARN"), result.checks
    assert result.checks["mps_headroom"].reason == "MPS_HEADROOM_OK"


def test_the_campaign_guard_binds_the_owner_birth_and_the_worker_count(tmp_path):
    """The scope is the real owner identity, the MPS selector and the exact worker count."""

    _, result = run_guard_phase(SimpleNamespace(evidence_root=tmp_path), policy=MPS_POLICY,
                                batch_id="b-n1", worker_count=1, probe=lambda **_: _healthy(),
                                state_root=_state_root(tmp_path))
    scope = result.scope

    assert scope.batch_id == "b-n1"
    assert scope.epoch == CAMPAIGN_GUARD_EPOCH
    assert scope.owner_pid == os.getpid()
    assert scope.owner_starttime_ticks > 0
    assert scope.gpu_selector == "MPS:default"
    assert scope.worker_count == 1


# --------------------------------------------------------------------------------------
# the one-shot handover across exec
# --------------------------------------------------------------------------------------


def test_the_handover_result_is_consumed_exactly_once(tmp_path):
    """The admitted result crosses the exec through one pipe and is read once."""

    scope = campaign_guard_scope(batch_id="b-n1", worker_count=1)
    result = run_campaign_start_guard(policy=MPS_POLICY, batch_id="b-n1", worker_count=1,
                                      probe=lambda **_: _healthy(),
                                      state_root=_state_root(tmp_path))
    read_fd, write_fd = os.pipe()
    try:
        publish_guard_handover(write_fd, result)
        consumed = consume_guard_handover(read_fd, scope=scope, max_age_s=10.0,
                                          forbidden_modules=())
        assert consumed.status in (PASS, "WARN")
        assert consumed.scope == scope
        with pytest.raises(GuardHandoverRefused, match="GUARD_HANDOVER_CLOSED"):
            consume_guard_handover(read_fd, scope=scope, max_age_s=10.0, forbidden_modules=())
    finally:
        for descriptor in (read_fd, write_fd):
            try:
                os.close(descriptor)
            except OSError:
                pass


@pytest.mark.parametrize(
    "mutate, reason",
    [
        (lambda payload: payload.update({"status": "FAIL"}), "GUARD_HANDOVER_NOT_ADMITTED"),
        (lambda payload: payload["scope"].update({"epoch": 5}), "GUARD_HANDOVER_SCOPE_MISMATCH"),
        (lambda payload: payload["scope"].update({"owner_pid": os.getpid() + 1}),
         "GUARD_HANDOVER_SCOPE_MISMATCH"),
        (lambda payload: payload["scope"].update({"owner_starttime_ticks": 1}),
         "GUARD_HANDOVER_SCOPE_MISMATCH"),
        (lambda payload: payload["scope"].update({"worker_count": 2}),
         "GUARD_HANDOVER_SCOPE_MISMATCH"),
        (lambda payload: payload["scope"].update({"gpu_selector": "INDEX:0"}),
         "GUARD_HANDOVER_SCOPE_MISMATCH"),
        (lambda payload: payload.update({"recorded_monotonic_s": time.monotonic() - 600.0}),
         "GUARD_HANDOVER_EXPIRED"),
    ],
)
def test_a_tampered_or_foreign_handover_document_is_refused(mutate, reason, tmp_path):
    """Scope, owner, epoch and age are all checked on the far side of the exec."""

    scope = campaign_guard_scope(batch_id="b-n1", worker_count=1)
    result = run_campaign_start_guard(policy=MPS_POLICY, batch_id="b-n1", worker_count=1,
                                      probe=lambda **_: _healthy(),
                                      state_root=_state_root(tmp_path))
    payload = guard_handover_document(result)
    mutate(payload)
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, json.dumps(payload).encode())
        os.close(write_fd)
        with pytest.raises(GuardHandoverRefused, match=reason):
            consume_guard_handover(read_fd, scope=scope, max_age_s=2.0, forbidden_modules=())
    finally:
        for descriptor in (read_fd, write_fd):
            try:
                os.close(descriptor)
            except OSError:
                pass


def test_the_broker_phase_refuses_without_the_inherited_pipe(tmp_path):
    """An existing PASS file on disk is not a substitute for the process-created pipe."""

    (tmp_path / "start-guard.json").write_text(json.dumps({"status": "PASS", "epoch": 0}))
    scope = campaign_guard_scope(batch_id="b-n1", worker_count=1)

    with pytest.raises(GuardHandoverRefused, match="GUARD_HANDOVER_MISSING"):
        broker_phase_guard({}, scope=scope, max_age_s=2.0)


def test_the_broker_phase_refuses_when_the_guard_phase_import_survives(tmp_path):
    """The broker phase must be a fresh interpreter state, or it is refused.

    `MpsBrokerBootstrap.require_import_order` refuses an interpreter that already has torch, so the
    admission refuses the same condition by name instead of letting the bootstrap discover it.
    """

    scope = campaign_guard_scope(batch_id="b-n1", worker_count=1)
    result = run_campaign_start_guard(policy=MPS_POLICY, batch_id="b-n1", worker_count=1,
                                      probe=lambda **_: _healthy(),
                                      state_root=_state_root(tmp_path))
    read_fd, write_fd = os.pipe()
    sentinel = "so101_guard_survived_import"
    try:
        publish_guard_handover(write_fd, result)
        sys.modules.setdefault(sentinel, object())
        try:
            with pytest.raises(GuardHandoverRefused, match="GUARD_PHASE_IMPORT_SURVIVED"):
                broker_phase_guard({GUARD_RESULT_FD_VARIABLE: str(read_fd)}, scope=scope,
                                   max_age_s=10.0, forbidden_modules=(sentinel,))
        finally:
            sys.modules.pop(sentinel, None)
    finally:
        for descriptor in (read_fd, write_fd):
            try:
                os.close(descriptor)
            except OSError:
                pass


def test_the_torch_import_of_the_guard_phase_does_not_cross_the_exec(tmp_path):
    """The real boundary: an exec clears the guard phase's imports before the broker phase.

    The module named `torch` is a sentinel on `PYTHONPATH`, which makes the proof independent of
    whether the installed torch can be imported on this host: what is being proved is that the
    guard phase's `sys.modules` does not survive the `exec`, and the sentinel stands in for the
    one import the broker bootstrap requires to be absent (`MPS_IMPORT_ORDER`).
    """

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "torch.py").write_text(
        "import os, pathlib\n"
        "pathlib.Path(os.environ['GUARD_TORCH_MARKER']).write_text('imported\\n')\n"
        "def marker():\n"
        "    return 'sentinel'\n")
    marker = tmp_path / "torch-imported.txt"
    phase_two = (
        "import json, os, sys\n"
        "from so101_demo.cli.macos_w2_campaign import (\n"
        "    GUARD_RESULT_FD_VARIABLE, broker_phase_guard, campaign_guard_scope)\n"
        "guard = broker_phase_guard(os.environ,\n"
        "                           scope=campaign_guard_scope(batch_id='b-n1', worker_count=1),\n"
        "                           max_age_s=30.0)\n"
        "print(json.dumps({'status': guard.status,\n"
        "                  'torch_modules': sorted(m for m in sys.modules"
        " if m.split('.')[0] == 'torch')}))\n"
    )
    phase_one = textwrap.dedent(
        f"""
        import json, os, sys
        import torch  # the sentinel: this is what must not survive the exec
        from so101_demo.parallel_batch.accelerator_probe import AcceleratorSnapshot
        from so101_demo.parallel_batch.start_guard import StartGuardPolicy
        from so101_demo.parallel_batch.start_guard_probe import (
            publish_guard_handover, run_campaign_start_guard)
        from so101_demo.cli.macos_w2_campaign import (
            GUARD_RESULT_FD_VARIABLE, GUARD_PHASE_VARIABLE, GUARD_PHASE, BROKER_PHASE,
            campaign_guard_scope)

        def healthy(**_: object):
            return AcceleratorSnapshot(
                kind="mps", selector="default", available_bytes=8 << 30,
                recommended_max_memory_bytes=16 << 30, current_allocated_memory_bytes=0,
                driver_allocated_memory_bytes=0,
                metric_source="unified-memory-proxy:vm_stat+torch.mps")

        result = run_campaign_start_guard(
            policy=StartGuardPolicy(mps_minimum_headroom_bytes=1 << 30),
            batch_id="b-n1", worker_count=1, probe=healthy,
            state_root=os.environ["SO101_TASK_ROOT"] + "/guard-state")
        read_fd, write_fd = os.pipe()
        publish_guard_handover(write_fd, result)
        os.set_inheritable(read_fd, True)
        environment = dict(os.environ)
        environment[GUARD_RESULT_FD_VARIABLE] = str(read_fd)
        environment[GUARD_PHASE_VARIABLE] = BROKER_PHASE
        os.execve(sys.executable, [sys.executable, "-c", {phase_two!r}], environment)
        """
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(scripts), environment.get("PYTHONPATH", "")])
    environment["GUARD_TORCH_MARKER"] = str(marker)
    environment["SO101_TASK_ROOT"] = str(tmp_path / "task-root")
    completed = subprocess.run([sys.executable, "-c", phase_one], capture_output=True, text=True,
                               env=environment, timeout=120)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["status"] == PASS
    assert payload["torch_modules"] == [], (
        "the guard phase's torch import must be gone before the broker phase starts")
    assert marker.is_file(), "the sentinel torch module was never imported by the guard phase"


def test_the_cli_guard_phase_hands_the_admission_over_through_its_own_pipe(tmp_path,
                                                                          monkeypatch):
    """The entry point's own handover: one inheritable descriptor, one consuming broker phase.

    The guard phase is driven for real (the probe is the one seam that is stubbed, because a real
    MPS read needs hardware and is exercised elsewhere); only the `exec` itself is replaced, so what
    is asserted here is the CLI's own wiring: the descriptor is created by this process, made
    inheritable, named in the environment, consumed exactly once by the broker phase, and the
    on-disk record is audit only.
    """

    import so101_demo.cli.macos_w2_campaign as cli
    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_v6
    from so101_demo.parallel_batch.w1_composition import compose_w1_first_pass

    class _ExecCalled(Exception):
        pass

    real_guard_phase = cli.run_guard_phase

    def stubbed_guard_phase(arguments, **kwargs):
        kwargs.setdefault("probe", lambda **_: _healthy())
        return real_guard_phase(arguments, **kwargs)

    monkeypatch.setattr(cli, "run_guard_phase", stubbed_guard_phase)
    captured = {}

    def fake_execve(executable, argv, environment):
        captured.update({"executable": executable, "argv": list(argv),
                         "environment": dict(environment)})
        raise _ExecCalled

    monkeypatch.setattr(cli.os, "execve", fake_execve)

    arguments = SimpleNamespace(evidence_root=tmp_path, batch_id="b-n1", campaign_id="b-n1")
    config = load_parallel_runtime_config_v6(V6_CONFIG)
    plan = compose_w1_first_pass(config=config, config_path=V6_CONFIG, campaign_id="b-n1",
                                 batch_id="b-n1", selected_point_ids=("p1",),
                                 evidence_root=tmp_path)
    document: dict = {}
    with pytest.raises(_ExecCalled):
        cli._guard_admission(arguments, ["--config", str(V6_CONFIG)], plan,
                             cli.route_spec("MPS_W1_FIRST_PASS"), document)

    assert captured["argv"][:3] == [sys.executable, "-m", "so101_demo.cli.macos_n1_first_pass"]
    environment = captured["environment"]
    assert environment[cli.GUARD_PHASE_VARIABLE] == cli.BROKER_PHASE
    assert environment["PYTORCH_ENABLE_MPS_FALLBACK"] == "0"
    descriptor = int(environment[GUARD_RESULT_FD_VARIABLE])
    assert os.get_inheritable(descriptor) is True, "the broker phase inherits this pipe"
    assert json.loads((tmp_path / "start-guard.json").read_text())["status"] in (PASS, "WARN")

    scope = campaign_guard_scope(batch_id="b-n1", worker_count=1)
    admitted = broker_phase_guard(environment, scope=scope, max_age_s=30.0,
                                 forbidden_modules=())
    assert admitted.status in (PASS, "WARN")
    with pytest.raises(GuardHandoverRefused, match="GUARD_HANDOVER_CLOSED"):
        broker_phase_guard(environment, scope=scope, max_age_s=30.0, forbidden_modules=())


def test_the_cli_guard_phase_refuses_before_the_handover_on_a_failed_admission(tmp_path,
                                                                              monkeypatch):
    """A FAIL admission returns a refusal document and never reaches the exec."""

    import so101_demo.cli.macos_w2_campaign as cli
    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_v6
    from so101_demo.parallel_batch.w1_composition import compose_w1_first_pass

    monkeypatch.setattr(cli.os, "execve",
                        lambda *_: pytest.fail("a refused admission must not exec"))
    # `probe=None` is the fail-closed Darwin composition: the policy carries the floor, so the
    # missing accelerator admission is a refusal rather than an unguarded start.
    real_guard_phase = cli.run_guard_phase
    monkeypatch.setattr(cli, "run_guard_phase",
                        lambda arguments, **kwargs: real_guard_phase(
                            arguments, **{**kwargs, "probe": None}))
    arguments = SimpleNamespace(evidence_root=tmp_path, batch_id="b-n1", campaign_id="b-n1")
    plan = compose_w1_first_pass(config=load_parallel_runtime_config_v6(V6_CONFIG),
                                 config_path=V6_CONFIG, campaign_id="b-n1", batch_id="b-n1",
                                 selected_point_ids=("p1",), evidence_root=tmp_path)
    document: dict = {}
    result = cli._guard_admission(arguments, ["--config", str(V6_CONFIG)], plan,
                                  cli.route_spec("MPS_W1_FIRST_PASS"), document)

    assert result is None
    assert document["status"] == "REFUSED" and document["stage"] == "start_guard"
    assert document["start_guard"]["reason"] == "MPS_ACCELERATOR_PROBE_MISSING"


def test_the_campaign_body_stops_on_a_refused_admission_before_the_broker_phase(tmp_path,
                                                                               monkeypatch):
    """The entry point's own body: a refused admission returns before any child or endpoint.

    This drives the real composition - the supervisor with its per-spawn guard, the campaign object
    and the guard phase - and asserts that a refusal stops it: no claim is taken, no broker is
    built and no Worker exists.
    """

    import so101_demo.cli.macos_w2_campaign as cli
    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_v6
    from so101_demo.parallel_batch.w1_composition import compose_w1_first_pass

    def refused_guard_phase(arguments, **kwargs):
        result = run_campaign_start_guard(policy=kwargs["policy"], batch_id=kwargs["batch_id"],
                                          worker_count=kwargs["worker_count"], probe=None,
                                          state_root=_state_root(tmp_path))
        return cli.guard_document(result), result

    monkeypatch.setattr(cli, "run_guard_phase", refused_guard_phase)

    point_ids = ("task_start", "cup_test_forward_5cm", "cup_test_left_5cm",
                 "cup_test_right_5cm")
    arguments = SimpleNamespace(
        evidence_root=tmp_path, campaign_id="b-n1", batch_id="b-n1", skip_models=False,
        yolo_weights=tmp_path / "yolo.pt", grounded_root=tmp_path / "grounded",
        worker_deadline_s=1.0, tamper_snapshot_sha=False, duplicate_probe=False,
        cancel_second_worker_after_served=0, crash_broker_after_served=0,
        point_id=point_ids, catalog=PACKAGE / "config/mujoco/moveit_expert_validation_points_v1.yaml",
        catalog_sha256=None, retry_root=None)
    plan = compose_w1_first_pass(config=load_parallel_runtime_config_v6(V6_CONFIG),
                                 config_path=V6_CONFIG, campaign_id="b-n1", batch_id="b-n1",
                                 selected_point_ids=point_ids, evidence_root=tmp_path)
    document: dict = {"status": "PENDING"}

    code = cli._drive_campaign(arguments, ["--config", str(V6_CONFIG)], plan,
                               cli.route_spec("MPS_W1_FIRST_PASS"), document)

    assert code == 4
    assert document["status"] == "REFUSED" and document["stage"] == "start_guard"
    assert document["start_guard"]["reason"] == "MPS_ACCELERATOR_PROBE_MISSING"
    assert not (tmp_path / "supervisor" / "owner-receipt.json").exists(), "no claim was taken"


def test_run_campaign_start_guard_uses_the_real_helper_for_the_cpu_and_ram_half(tmp_path):
    """The fresh campaign guard is the real composition, not a decision double."""

    result = run_campaign_start_guard(policy=MPS_POLICY, batch_id="b-n1", worker_count=1,
                                      state_root=tmp_path / "state",
                                      probe=lambda **_: _healthy())
    assert result.status in (PASS, "WARN")
    # the helper's own checks survive the accelerator merge
    assert {"cpu_capacity", "cpu_busy", "ram"} <= set(result.checks)
    assert result.cleanup_state == "CLEAR"

    # `probe=None` is the fail-closed composition: the Darwin policy demands the MPS admission.
    refused = run_campaign_start_guard(policy=MPS_POLICY, batch_id="b-n1", worker_count=1,
                                       state_root=tmp_path / "state", probe=None)
    assert refused.status == FAIL
    assert refused.checks["mps_accelerator"].reason == "MPS_ACCELERATOR_PROBE_MISSING"


def test_the_w1_policy_of_the_installed_document_demands_the_mps_probe(tmp_path):
    """A v5/v6 policy carries the floor, so the MPS admission is mandatory, not optional."""

    policy = load_parallel_runtime_config_v6(V6_CONFIG).start_guard
    assert policy.mps_minimum_headroom_bytes == 1 << 30
    result = run_campaign_start_guard(policy=policy, batch_id="b-n1", worker_count=1,
                                      state_root=tmp_path / "state2",
                                      probe=lambda **_: _healthy())
    assert result.checks["mps_headroom"].status == PASS
