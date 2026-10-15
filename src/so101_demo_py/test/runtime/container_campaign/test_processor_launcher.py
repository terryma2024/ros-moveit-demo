"""The production processor factory: private directories, spec, launch record, and the amended mounts (A1)."""

import json
from pathlib import Path

import pytest

from so101_demo.runtime.container_campaign.processor_launcher import ContainerProcessorLauncher, all_phase1_attempts
from so101_teleop.unified.worker_slots import ActWorkerSlot
from test_processor_owner import Fixture

ATTEMPTS = (
    "wave-0/w00/g1/output/tasks/wave-0-w00-scene-01/attempts/scene-01/scene-01-lease-1/sealed",
    "wave-0/w01/g1/output/tasks/wave-0-w01-scene-02/attempts/scene-02/scene-02-lease-1/sealed",
    "wave-1/w00/g2/output/tasks/wave-1-w00-scene-03/attempts/scene-03/scene-03-lease-1/sealed",
)


def launcher_world(tmp_path):
    fixture = Fixture(tmp_path)
    run = fixture.paths["run"]
    for relative in ATTEMPTS:
        (run / relative).mkdir(parents=True, exist_ok=True)
    # things that are not a phase-1 sealed attempt directory
    (run / "wave-0/w00/g1/output/tasks/wave-0-w00-scene-01/attempts/scene-01/scene-01-lease-1/working").mkdir(parents=True)
    (run / "wave-0/w00/g1/tmp").mkdir(parents=True, exist_ok=True)
    runtime = json.loads(fixture.spec_path.read_text())["parallel_runtime"]
    launcher = ContainerProcessorLauncher(context=fixture.context, images={role: fixture.image for role in ("head", "teacher", "shard")}, paths=fixture.paths,
        registry=fixture.registry, parallel_runtime=runtime, approved_inputs=(), config_paths=(),
        docker_runner=fixture.docker, namespace_reader=lambda pid: 1)
    return fixture, launcher


def slot(fixture, name="p05"):
    return ActWorkerSlot(fixture.context.campaign_id, name, fixture.context.execution_generation)


def test_every_sealed_attempt_of_every_wave_is_found_and_nothing_else(tmp_path):
    fixture, _ = launcher_world(tmp_path)
    run = fixture.paths["run"]
    assert all_phase1_attempts(run) == tuple(sorted([fixture.attempt, *(run / relative for relative in ATTEMPTS)]))
    fixture.registry.close()


def test_a_processor_mounts_every_phase1_attempt_read_only_and_one_writable_processing_tree(tmp_path):
    fixture, launcher = launcher_world(tmp_path)
    run = fixture.paths["run"]
    # slot p01 is handed the scene whose sealed attempt a "p00-only" rule would not have mounted
    for name in ("p01", "p02"):
        owner = launcher(slot=slot(fixture, name), generation=1)
        mounts = [owner.argv[i + 1] for i, value in enumerate(owner.argv) if value == "--mount"]
        for relative in ATTEMPTS:
            path = run / relative
            assert f"type=bind,src={path},dst={path},readonly" in mounts
        writable = [m for m in mounts if "readonly" not in m]
        assert f"type=bind,src={run / 'processing'},dst={run / 'processing'}" in writable
        assert not any(f"src={run / 'wave-0'}," in m or f"src={run / 'host'}," in m for m in mounts)
    fixture.registry.close()


def test_the_launch_is_the_slot_and_generation_with_its_private_directories_and_spec(tmp_path):
    fixture, launcher = launcher_world(tmp_path)
    run = fixture.paths["run"]
    owner = launcher(slot=slot(fixture, "p03"), generation=2)
    root = run / "processing/p03/g2"
    assert owner.launch.launch_id == "processing-p03-g2" and owner.launch.role == "processor"
    assert owner.launch.owned_root == str(root) and owner.launch.worker_id == "p03" and owner.launch.launch_generation == 2
    assert all((root / name).is_dir() for name in ("tmp", "control", "output", "task-inputs"))
    spec = json.loads((run / "processor-p03-g2.json").read_text())
    assert spec["processor_id"] == "p03" and spec["launch_generation"] == 2 and spec["owned_root"] == str(root)
    with pytest.raises(FileExistsError):
        launcher(slot=slot(fixture, "p03"), generation=2)   # a generation is never reused
    fixture.registry.close()


@pytest.mark.parametrize("problem", ["wave_slot", "foreign_campaign", "generation_zero", "no_attempts"])
def test_a_bad_slot_or_a_run_without_phase1_attempts_is_refused(tmp_path, problem):
    fixture, launcher = launcher_world(tmp_path)
    bad = {"wave_slot": slot(fixture, "w00"),
           "foreign_campaign": ActWorkerSlot("other", "p00", fixture.context.execution_generation)}.get(problem, slot(fixture))
    if problem == "no_attempts":
        for path in (fixture.attempt, *(fixture.paths["run"] / relative for relative in ATTEMPTS)):
            Path(path).rmdir()
    with pytest.raises(ValueError, match="PROCESSOR_LAUNCH"):
        launcher(slot=bad, generation=0 if problem == "generation_zero" else 1)
    fixture.registry.close()
