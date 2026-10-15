"""The processor owner: durable intent before Docker, readiness from the program's ready file, stop proof from the container exit."""

import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from so101_demo.runtime.container_campaign import processor_owner as owner_module
from so101_demo.runtime.container_campaign.launch import ProcessorLaunchArgs
from so101_demo.runtime.container_campaign.paths import make_campaign_paths
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_teleop.unified.contracts import AdmittedCampaignContext

GPU = "GPU-28221cec-9d21-7753-fd5a-da645740df19"
CID = "c" * 64
STARTED = "2026-10-15T01:02:03.123Z"
TOKEN = "e" * 64
ATTEMPT = "wave-0/w01/g1/output/tasks/task-1/attempts/scene-01/scene-01-lease-1/sealed"


class Fixture:
    def __init__(self, tmp_path, *, response=(0, CID)):
        self.paths = make_campaign_paths(tmp_path, "campaign")
        run = self.paths["run"]
        self.root = run / "processing" / "p00" / "g1"
        for name in ("tmp", "control", "output", "task-inputs"):
            (self.root / name).mkdir(parents=True)
        self.attempt = run / ATTEMPT
        self.attempt.mkdir(parents=True)
        runtime = run / "runtime.yaml"
        runtime.write_bytes((Path(__file__).resolve().parents[3] / "config/mujoco/parallel_batch_linux_cuda.yaml").read_bytes())
        self.image = dict(digest="sha256:" + "a" * 64, package_source_sha256="b" * 64, install_sha256="c" * 64)
        self.spec_path = run / "processor-p00-g1.json"
        self.deadline = time.monotonic() + 3600
        self.spec = dict(schema_version=1, kind="ACT_CONTAINER_PROCESSOR", campaign_id="campaign", processor_id="p00",
            launch_generation=1, execution_generation=1, runtime_id="runtime-p00", service_epoch="epoch", service_token=TOKEN,
            owned_root=str(self.root), processing_root=str(run / "processing"),
            parallel_runtime=dict(path=str(runtime), sha256=hashlib.sha256(runtime.read_bytes()).hexdigest()),
            deadline_monotonic_s=self.deadline)
        self.spec_path.write_text(json.dumps(self.spec))
        self.context = AdmittedCampaignContext(campaign_id="campaign", operation_id="operation",
            workload_kind="act_collection_start", service_epoch="epoch", execution_generation=1, stable_host_id="host",
            physical_gpu_uuid=GPU, worker_count=1, source_sha256="d" * 64, manifest_sha256="d" * 64,
            runtime_config_sha256="d" * 64, collection_config_sha256="d" * 64, contact_policy_fingerprint="d" * 64,
            domain_session_map_sha256="d" * 64, resource_binding_id="binding", evidence_root=str(run),
            admitted_at_monotonic_s=1, deadline_monotonic_s=time.monotonic() + 7200, registered_evidence_root=str(tmp_path),
            campaign_config_path=str(self.spec_path), campaign_config_sha256="d" * 64)
        self.launch = ContainerLaunch(launch_id="processing-p00-g1", role="processor", worker_id="p00", wave_id=None,
            launch_generation=1, container_name="so101-act-p00-g1", image_digest=self.image["digest"],
            owned_root=str(self.root), session_id=None)
        self.registry = ContainerLaunchRegistry(self.paths["host"] / "launches.sqlite3")
        self.calls = []
        self.response = response
        self.state = dict(Running=True, Restarting=False, Pid=900, Status="running", ExitCode=0, StartedAt=STARTED, OOMKilled=False)

    def inspect_document(self):
        return dict(Id=CID, Image=self.image["digest"], Name="/" + self.launch.container_name, State=dict(self.state))

    def docker(self, argv):
        self.calls.append(argv)
        if argv[:2] == ["docker", "run"]:
            assert self.registry.records()[0]["launch"] == asdict(self.launch), "intent is durable before Docker runs"
            return SimpleNamespace(returncode=self.response[0], stdout=self.response[1], stderr="diagnostic")
        if argv[:2] == ["docker", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps([self.inspect_document()]), stderr="")
        raise AssertionError(argv)

    def owner(self, **overrides):
        kwargs = dict(admitted_context=self.context, launch=self.launch, entry=ProcessorLaunchArgs(spec=self.spec_path),
            images={role: self.image for role in ("head", "teacher", "shard")}, paths=self.paths, registry=self.registry,
            approved_inputs=(), config_paths=(self.spec_path,), phase1_attempts=(self.attempt,), service_token=TOKEN,
            startup_timeout_s=2., status_timeout_s=5., max_frame_bytes=8388608, stop_timeout_s=.2, docker_runner=self.docker,
            namespace_reader=lambda pid: 4026531999)
        kwargs.update(overrides)
        return owner_module.ContainerProcessorOwner(**kwargs)

    def child_files(self, process_owner):
        """What the program leaves in its directories once it serves."""
        ready = {"schema_version": 1, "kind": "container_child_ready", "generation": 1, "process_owner": process_owner,
                 "pid_namespace_inode": 4026531999, "service_epoch": "epoch", "runtime_id": "runtime-p00",
                 "campaign_id": "campaign", "worker_id": "p00", "execution_generation": 1,
                 "normal_socket": "/act/control/normal.sock", "safety_socket": "/act/control/safety.sock"}
        (self.root / "control/child-ready.json").write_text(json.dumps(ready))
        (self.root / "processor-ready.json").write_text(json.dumps(dict(schema_version=1, kind="ACT_PROCESSOR_RUNTIME_READY",
            generation=1, process_owner=process_owner)))


PROCESS = dict(pid=1, pgid=1, started_ticks=7, argv_sha256="e" * 64, environment_sha256="f" * 64)


def test_owner_builds_the_processor_argv_from_the_admitted_launch(tmp_path):
    fixture = Fixture(tmp_path)
    owner = fixture.owner()
    argv = owner.argv
    assert "--gpus" not in argv and argv[-3:] == ["campaign_processor", "--spec", str(fixture.spec_path)]
    assert argv[-4] == fixture.image["digest"] and owner.teacher_socket is None
    assert f"type=bind,src={fixture.attempt},dst={fixture.attempt},readonly" in [argv[i + 1] for i, v in enumerate(argv) if v == "--mount"]
    fixture.registry.close()


@pytest.mark.parametrize("problem", ["role", "token", "processor_id", "image", "outside_processing", "deadline", "attempts_type"])
def test_owner_refuses_a_launch_that_is_not_this_processor(tmp_path, problem):
    fixture = Fixture(tmp_path)
    overrides = {}
    if problem == "role":
        overrides["launch"] = ContainerLaunch(launch_id="head-g1", role="head", worker_id=None, wave_id=None, launch_generation=1,
            container_name="so101-head", image_digest=fixture.image["digest"], owned_root=str(fixture.paths["services"]["head"]))
    elif problem == "token":
        overrides["service_token"] = "0" * 64
    elif problem == "processor_id":
        spec = dict(fixture.spec, processor_id="p01")
        fixture.spec_path.write_text(json.dumps(spec))
    elif problem == "image":
        overrides["images"] = {role: dict(fixture.image, digest="sha256:" + "9" * 64) for role in ("head", "teacher", "shard")}
    elif problem == "outside_processing":
        overrides["launch"] = ContainerLaunch(launch_id="processing-p00-g1", role="processor", worker_id="p00", wave_id=None,
            launch_generation=1, container_name="so101-act-p00-g1", image_digest=fixture.image["digest"],
            owned_root=str(fixture.paths["services"]["head"]))
    elif problem == "deadline":
        fixture.spec_path.write_text(json.dumps(dict(fixture.spec, deadline_monotonic_s=fixture.context.deadline_monotonic_s + 100)))
    elif problem == "attempts_type":
        overrides["phase1_attempts"] = [fixture.attempt]
    with pytest.raises(ValueError):
        fixture.owner(**overrides)
    fixture.registry.close()


@pytest.mark.parametrize("response", [(1, ""), (0, "not-a-container-id")])
def test_a_failed_launch_keeps_the_intent_and_never_claims_cleanup(tmp_path, response):
    fixture = Fixture(tmp_path, response=response)
    owner = fixture.owner()

    async def run():
        with pytest.raises(ValueError, match="PROCESSOR_CONTAINER_LAUNCH_FAILED"):
            await owner.start()
        closed = await owner.close()
        assert closed["terminated"] is False and closed["errors"][0]["reason"] == "LAUNCH_OWNER_UNKNOWN"
        assert fixture.registry.records()[0]["owner"] is None
        assert (fixture.root / "launch-result.json").is_file() and (fixture.root / "launch-argv.json").is_file()
    try:
        asyncio.run(run())
    finally:
        fixture.registry.close()


def test_spec_drift_is_refused_before_intent_or_docker(tmp_path):
    fixture = Fixture(tmp_path)
    owner = fixture.owner()
    fixture.spec_path.write_text("{}")

    async def run():
        with pytest.raises(ValueError, match="PROCESSOR_SPEC_CHANGED"):
            await owner.start()
        assert fixture.registry.records() == () and fixture.calls == []
    try:
        asyncio.run(run())
    finally:
        fixture.registry.close()


def provenance(image, *, digest=None):
    return lambda cid, docker_runner: dict(container_id=cid, docker_started_at=STARTED, image_digest=digest or image["digest"],
        provenance={name: image[name] for name in ("package_source_sha256", "install_sha256")})


def test_ready_file_provenance_and_exit_proof(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)
    fixture.child_files(PROCESS)
    monkeypatch.setattr(owner_module, "read_container_provenance", provenance(fixture.image))
    owner = fixture.owner()

    async def run():
        binding = await owner.start()
        assert binding.process.pid == 1 and await owner.check_health()
        record = fixture.registry.records()[0]
        assert record["owner"]["container_id"] == CID and record["binding"] is not None
        assert (fixture.root / "actual-container-provenance.json").is_file()
        # the running container is not proven stopped; its exit inspect is the whole proof
        proof = await owner.prove_stopped()
        assert proof["terminated"] is False
        fixture.state.update(Running=False, Pid=0, Status="exited")
        proof = await owner.prove_stopped()
        assert proof == dict(terminated=True, launch_id="processing-p00-g1", errors=[])
        assert fixture.registry.records()[0]["exit_inspect"]["State"]["Status"] == "exited"
    try:
        asyncio.run(run())
    finally:
        fixture.registry.close()


def test_a_changed_image_fails_the_start(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)
    fixture.child_files(PROCESS)
    monkeypatch.setattr(owner_module, "read_container_provenance", provenance(fixture.image, digest="sha256:" + "8" * 64))
    owner = fixture.owner()

    async def run():
        with pytest.raises(ValueError, match="PROCESSOR_IMAGE_PROVENANCE_CHANGED"):
            await owner.start()
    try:
        asyncio.run(run())
    finally:
        fixture.registry.close()


def test_a_ready_record_of_another_process_fails_the_start(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)
    fixture.child_files(PROCESS)
    (fixture.root / "processor-ready.json").write_text(json.dumps(dict(schema_version=1, kind="ACT_PROCESSOR_RUNTIME_READY",
        generation=1, process_owner=dict(PROCESS, pid=2))))
    monkeypatch.setattr(owner_module, "read_container_provenance", provenance(fixture.image))
    owner = fixture.owner()

    async def run():
        with pytest.raises(ValueError, match="PROCESSOR_RUNTIME_READINESS_INVALID"):
            await owner.start()
    try:
        asyncio.run(run())
    finally:
        fixture.registry.close()
