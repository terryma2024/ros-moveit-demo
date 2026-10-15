"""The Host prepares a native processor: the same private directories and spec a container processor gets, a native owner.

Real: the launcher, the spec loader, the launch registry and owner construction. Nothing is started.
"""

import json
from pathlib import Path
import sys

import pytest

from so101_demo.runtime.container_campaign.native_launcher import NATIVE_PROCESSOR_MODULE, NativeProcessorLauncher
from so101_demo.runtime.container_campaign.native_processor_owner import NativeProcessorOwner
from so101_demo.runtime.container_campaign.processor_launcher import ContainerProcessorLauncher
from so101_teleop.unified.worker_slots import ActWorkerSlot
from test_processor_launcher import ATTEMPTS, launcher_world, slot
from test_processor_owner import Fixture


def native_world(tmp_path, **overrides):
    fixture = Fixture(tmp_path)
    run = fixture.paths["run"]
    for relative in ATTEMPTS:
        (run / relative).mkdir(parents=True, exist_ok=True)
    runtime = json.loads(fixture.spec_path.read_text())["parallel_runtime"]
    arguments = dict(context=fixture.context, paths=fixture.paths, registry=fixture.registry, parallel_runtime=runtime,
        approved_inputs=(), config_paths=(), install_prefix=tmp_path / "install",
        base_environment=dict(PATH="/usr/bin", ROS_NAMESPACE="/stale", CUDA_VISIBLE_DEVICES="3"))
    return fixture, NativeProcessorLauncher(**(arguments | overrides))


def test_the_native_launcher_writes_the_same_spec_a_container_gets_and_a_native_owner(tmp_path):
    fixture, launcher = native_world(tmp_path)
    run = fixture.paths["run"]
    owner = launcher(slot=slot(fixture, "p03"), generation=2)
    root = run / "processing/p03/g2"
    written = json.loads((run / "processor-p03-g2.json").read_text())
    assert type(owner) is NativeProcessorOwner and owner.spec == written
    assert written["kind"] == "ACT_CONTAINER_PROCESSOR" and written["owned_root"] == str(root)
    launch = owner.launch
    assert launch.launcher == "native" and launch.role == "processor" and launch.container_name is None
    assert launch.image_digest is None and launch.session_id is None and launch.wave_id is None
    assert launch.launch_id == "processing-p03-g2" and launch.owned_root == str(root) and launch.launch_generation == 2
    assert all((root / name).is_dir() for name in ("tmp", "control", "output", "task-inputs"))
    assert owner.argv == [sys.executable, "-m", NATIVE_PROCESSOR_MODULE, "--spec", str(run / "processor-p03-g2.json"),
                          "--install-prefix", str(tmp_path / "install")]
    assert owner.environment["PATH"] == "/usr/bin" and owner.environment["CUDA_VISIBLE_DEVICES"] == ""
    assert "ROS_NAMESPACE" not in owner.environment and owner.environment["SO101_ACT_INSTANCE_ROOT"] == str(root)
    runtime = launcher.runtime
    assert owner.startup_budget == runtime.initializing_hard_timeout_s and owner.status_budget == runtime.heartbeat_timeout_s
    assert owner.stop_budget == runtime.worker_recovery_timeout_s
    with pytest.raises(FileExistsError):
        launcher(slot=slot(fixture, "p03"), generation=2)   # a generation is never reused
    fixture.registry.close()


def test_the_native_and_the_container_launcher_write_equal_specs_for_the_same_slot(tmp_path):
    (tmp_path / "container").mkdir()
    (tmp_path / "native").mkdir()
    container_fixture, container = launcher_world(tmp_path / "container")
    native_fixture, native = native_world(tmp_path / "native")
    try:
        container(slot=slot(container_fixture, "p01"), generation=1)
        native(slot=slot(native_fixture, "p01"), generation=1)
        left = json.loads((container_fixture.paths["run"] / "processor-p01-g1.json").read_text())
        right = json.loads((native_fixture.paths["run"] / "processor-p01-g1.json").read_text())
        assert set(left) == set(right)
        differing = {key for key in left if left[key] != right[key]}
        assert differing <= {"service_token", "owned_root", "processing_root", "parallel_runtime", "deadline_monotonic_s", "runtime_id"}
        assert {key: left[key] for key in ("campaign_id", "processor_id", "launch_generation", "execution_generation",
                                            "service_epoch", "kind", "schema_version")} == \
            {key: right[key] for key in ("campaign_id", "processor_id", "launch_generation", "execution_generation",
                                         "service_epoch", "kind", "schema_version")}
    finally:
        container_fixture.registry.close()
        native_fixture.registry.close()


@pytest.mark.parametrize("problem", ["wave_slot", "foreign_campaign", "generation_zero", "no_attempts"])
def test_a_bad_slot_or_a_run_without_phase1_attempts_is_refused(tmp_path, problem):
    fixture, launcher = native_world(tmp_path)
    bad = {"wave_slot": slot(fixture, "w00"),
           "foreign_campaign": ActWorkerSlot("other", "p00", fixture.context.execution_generation)}.get(problem, slot(fixture))
    if problem == "no_attempts":
        for path in (fixture.attempt, *(fixture.paths["run"] / relative for relative in ATTEMPTS)):
            Path(path).rmdir()
    with pytest.raises(ValueError, match="PROCESSOR_LAUNCH"):
        launcher(slot=bad, generation=0 if problem == "generation_zero" else 1)
    fixture.registry.close()


@pytest.mark.parametrize("problem", ["relative_prefix", "two_workers", "container_launcher_images"])
def test_the_native_launcher_is_for_one_worker_and_an_absolute_installed_prefix(tmp_path, problem):
    fixture = Fixture(tmp_path)
    runtime = json.loads(fixture.spec_path.read_text())["parallel_runtime"]
    context = fixture.context if problem != "two_workers" else type(fixture.context)(**{
        **fixture.context.__dict__, "worker_count": 2})
    arguments = dict(context=context, paths=fixture.paths, registry=fixture.registry, parallel_runtime=runtime,
                     approved_inputs=(), config_paths=(), install_prefix=Path("install") if problem == "relative_prefix" else tmp_path)
    if problem == "container_launcher_images":
        arguments["images"] = {}
    with pytest.raises((ValueError, TypeError)):
        NativeProcessorLauncher(**arguments)
    fixture.registry.close()


def test_the_native_launcher_is_a_processor_launcher(tmp_path):
    fixture, launcher = native_world(tmp_path)
    assert isinstance(launcher, ContainerProcessorLauncher)
    fixture.registry.close()
