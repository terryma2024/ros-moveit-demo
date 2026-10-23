"""Read actual image bytes and origins, not a label or commit claim."""

import copy
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def fixture(tmp_path):
    module = importlib.import_module("so101_demo.runtime.container_campaign.provenance")
    source, install = tmp_path/"source", tmp_path/"install"
    source.mkdir(); install.mkdir()
    (source/"worker.py").write_text("source")
    (source/".image-git.json").write_text(json.dumps(dict(git_commit="a"*40,
        submodules={"vendor/controllers": "b"*40})))
    (install/"worker.py").write_text("installed")
    runtime = dict(interpreter="/act/venv/bin/python", dependencies={"numpy": "1.26.4"},
        module_origins={"so101_demo": "/act/install/lib/so101_demo/__init__.py"},
        package_prefixes={"so101_demo_py": "/act/install"})
    manifest = module.freeze_image(source_root=source, install_root=install,
        git_commit="a"*40, submodules={"vendor/controllers": "b"*40}, runtime=runtime)
    return module, source, install, runtime, manifest


def test_original_freeze_reads_back_all_bytes_and_runtime(tmp_path):
    module, source, install, runtime, manifest = fixture(tmp_path)
    report = module.verify_image_freeze(manifest, source_root=source, install_root=install,
                                       runtime=runtime)
    assert report["package_source_sha256"] == manifest["source"]["sha256"]
    assert report["install_sha256"] == manifest["install"]["sha256"]
    assert report["runtime"] == runtime
    assert manifest["source"]["git_commit"] == "a"*40


@pytest.mark.parametrize("problem", ["source", "install", "extra_file", "dependency", "origin", "prefix", "python", "hash", "metadata", "metadata_identity", "extra_field"])
def test_drift_refuses_provenance(tmp_path, problem):
    module, source, install, runtime, manifest = fixture(tmp_path)
    if problem == "source": (source/"worker.py").write_text("different")
    elif problem == "install": (install/"worker.py").write_text("different")
    elif problem == "extra_file": (install/"injected.py").write_text("injected")
    elif problem == "dependency": runtime["dependencies"]["numpy"] = "other"
    elif problem == "origin": runtime["module_origins"]["so101_demo"] = "/act/source/src/worker.py"
    elif problem == "prefix": runtime["package_prefixes"]["so101_demo_py"] = "/host/install"
    elif problem == "python": runtime["interpreter"] = "/usr/bin/python3"
    elif problem == "hash": manifest["install"]["sha256"] = "f"*64
    elif problem == "metadata": manifest["source"]["git_commit"] = "main"
    elif problem == "metadata_identity": manifest["source"]["git_commit"] = "f"*40
    elif problem == "extra_field": manifest["label_pass"] = True
    with pytest.raises(ValueError, match="IMAGE_PROVENANCE_INVALID"):
        module.verify_image_freeze(manifest, source_root=source, install_root=install, runtime=runtime)


def test_safe_internal_link_is_bound_but_external_source_link_is_rejected(tmp_path):
    module, source, install, runtime, _manifest = fixture(tmp_path)
    (install/"current.py").symlink_to("worker.py")
    manifest = module.freeze_image(source_root=source, install_root=install,
        git_commit="a"*40, submodules={"vendor/controllers": "b"*40}, runtime=runtime)
    module.verify_image_freeze(manifest, source_root=source, install_root=install, runtime=runtime)
    (install/"outside.py").symlink_to(source/"worker.py")
    with pytest.raises(ValueError, match="IMAGE_PROVENANCE_INVALID"):
        module.freeze_image(source_root=source, install_root=install,
            git_commit="a"*40, submodules={"vendor/controllers": "b"*40}, runtime=runtime)


@pytest.mark.parametrize("problem", [None, "cli_failed", "exec_failed", "restart", "not_running", "label_only", "duplicate", "wrong_id"])
def test_docker_readback_binds_live_image_identity_and_actual_probe(tmp_path, problem, monkeypatch):
    module, source, install, runtime, manifest = fixture(tmp_path)
    monkeypatch.setattr(module, "_sleep", lambda _seconds: None)
    report = module.verify_image_freeze(manifest, source_root=source, install_root=install, runtime=runtime)
    container_id = "1"*64
    inspect = dict(Id=container_id, Image="sha256:"+"2"*64,
                   State=dict(Running=True, Restarting=False, Pid=800,
                              StartedAt="2026-10-12T01:02:03.123456789Z"))
    calls = []
    def docker_runner(argv):
        calls.append(argv)
        if argv[:2] == ["docker", "inspect"]:
            document = copy.deepcopy(inspect)
            if problem == "restart" and len(calls)>1: document["State"]["StartedAt"] = "2026-10-12T02:02:03Z"
            if problem == "not_running": document["State"]["Running"] = False
            if problem == "wrong_id": document["Id"] = "3"*64
            return SimpleNamespace(returncode=int(problem=="cli_failed"), stdout=json.dumps([document]))
        assert argv == ["docker", "exec", container_id, "/act/venv/bin/python", "-I", "-m",
                        "so101_demo.runtime.container_campaign.provenance"]
        payload = json.dumps(report)
        if problem == "label_only": payload = '{"git_commit":"'+"a"*40+'","PASS":true}'
        if problem == "duplicate": payload = '{"schema_version":1,"schema_version":1}'
        return SimpleNamespace(returncode=int(problem=="exec_failed"), stdout=payload)
    if problem is None:
        actual = module.read_container_provenance(container_id, docker_runner=docker_runner)
        assert actual["image_digest"] == inspect["Image"] and actual["container_id"] == container_id
        assert actual["provenance"] == report
        assert len(calls)==3
    else:
        with pytest.raises(ValueError, match="IMAGE_PROVENANCE_INVALID"):
            module.read_container_provenance(container_id, docker_runner=docker_runner)


class StartingContainer:
    """A docker stand-in whose first reads fail the way a container does just after `docker run`."""

    def __init__(self, module, report, *, inspect_fails=0, not_running=0, exec_fails=0, payloads=None, restart_at=None):
        self.id = "1" * 64
        self.report = report
        self.inspect_fails, self.not_running, self.exec_fails = inspect_fails, not_running, exec_fails
        self.payloads = list(payloads or [])
        self.restart_at = restart_at
        self.inspects = self.execs = 0

    def __call__(self, argv):
        if argv[:2] == ["docker", "inspect"]:
            self.inspects += 1
            if self.inspect_fails:
                self.inspect_fails -= 1
                return SimpleNamespace(returncode=1, stdout="", stderr="")
            running = not self.not_running
            self.not_running -= 0 if running else 1
            started = "2026-10-12T02:02:03Z" if self.restart_at is not None and self.inspects >= self.restart_at else "2026-10-12T01:02:03Z"
            document = dict(Id=self.id, Image="sha256:" + "2" * 64,
                            State=dict(Running=running, Restarting=False, Pid=800 if running else 0, StartedAt=started))
            return SimpleNamespace(returncode=0, stdout=json.dumps([document]), stderr="")
        self.execs += 1
        if self.exec_fails:
            self.exec_fails -= 1
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout=self.payloads.pop(0) if self.payloads else json.dumps(self.report))


def retry_fixture(tmp_path, monkeypatch, **faults):
    module, source, install, runtime, manifest = fixture(tmp_path)
    report = module.verify_image_freeze(manifest, source_root=source, install_root=install, runtime=runtime)
    pauses = []
    monkeypatch.setattr(module, "_sleep", pauses.append)
    return module, report, StartingContainer(module, report, **faults), pauses


@pytest.mark.parametrize("faults, pauses", [
    (dict(inspect_fails=1), [0.5]), (dict(not_running=2), [0.5, 1.0]), (dict(exec_fails=3), [0.5, 1.0, 2.0]),
    (dict(inspect_fails=1, not_running=1, exec_fails=1), [0.5, 1.0, 2.0])])
def test_a_container_that_is_not_up_yet_is_read_again_and_the_read_is_compared_once(tmp_path, monkeypatch, faults, pauses):
    module, report, docker, slept = retry_fixture(tmp_path, monkeypatch, **faults)
    actual = module.read_container_provenance(docker.id, docker_runner=docker)
    assert actual["provenance"] == report and actual["container_id"] == docker.id
    assert slept == pauses


@pytest.mark.parametrize("faults", [dict(inspect_fails=99), dict(not_running=99), dict(exec_fails=99)])
def test_a_read_that_never_succeeds_is_refused_after_the_bounded_attempts(tmp_path, monkeypatch, faults):
    module, _report, docker, slept = retry_fixture(tmp_path, monkeypatch, **faults)
    with pytest.raises(ValueError, match="IMAGE_PROVENANCE_INVALID"):
        module.read_container_provenance(docker.id, docker_runner=docker)
    assert slept == list(module.READ_PAUSES_S) and module.READ_ATTEMPTS == len(slept) + 1
    assert sum(slept) <= 3.5 and (docker.inspects <= module.READ_ATTEMPTS + 1)


@pytest.mark.parametrize("payload", ['{"git_commit":"' + "a" * 40 + '","PASS":true}', '{"schema_version":1,"schema_version":1}', "not json", ""])
def test_a_report_that_was_read_but_is_wrong_is_never_read_again(tmp_path, monkeypatch, payload):
    module, _report, docker, slept = retry_fixture(tmp_path, monkeypatch, payloads=[payload])
    with pytest.raises(ValueError, match="IMAGE_PROVENANCE_INVALID"):
        module.read_container_provenance(docker.id, docker_runner=docker)
    assert slept == [] and docker.execs == 1


def test_a_wrong_report_after_a_retry_is_still_refused(tmp_path, monkeypatch):
    module, _report, docker, slept = retry_fixture(tmp_path, monkeypatch, exec_fails=1, payloads=['{"git_commit":"' + "a" * 40 + '"}'])
    with pytest.raises(ValueError, match="IMAGE_PROVENANCE_INVALID"):
        module.read_container_provenance(docker.id, docker_runner=docker)
    assert slept == [0.5] and docker.execs == 2


def test_a_container_that_restarts_between_the_two_inspects_is_not_read_again(tmp_path, monkeypatch):
    module, _report, docker, slept = retry_fixture(tmp_path, monkeypatch, restart_at=2)
    with pytest.raises(ValueError, match="IMAGE_PROVENANCE_INVALID"):
        module.read_container_provenance(docker.id, docker_runner=docker)
    assert slept == [] and docker.execs == 1 and docker.inspects == 2


def test_another_container_id_is_never_read_again(tmp_path, monkeypatch):
    module, _report, docker, slept = retry_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="IMAGE_PROVENANCE_INVALID"):
        module.read_container_provenance("3" * 64, docker_runner=docker)
    assert slept == [] and docker.execs == 0


def test_shard_prefix_readback_covers_the_patched_controller_overlay():
    """The overlay must resolve inside /act/install; an apt fallback would read back /opt/ros/jazzy and be refused."""
    module = importlib.import_module("so101_demo.runtime.container_campaign.provenance")
    shard = set(module.SHARD_PACKAGES)
    assert {"joint_trajectory_controller", "joint_state_broadcaster", "so101_queued_state_publisher",
            "controller_manager"} <= shard
    assert module.INFERENCE_PACKAGES == ("so101_demo_py",)
    runtime = dict(interpreter="/act/venv/bin/python", dependencies={"numpy": "1.26.4"},
        module_origins={"so101_demo": "/act/install/lib/so101_demo/__init__.py"},
        package_prefixes={name: "/act/install" for name in module.SHARD_PACKAGES})
    module._runtime_contract(runtime)
    runtime["package_prefixes"]["joint_trajectory_controller"] = "/opt/ros/jazzy"
    with pytest.raises(ValueError, match="IMAGE_PROVENANCE_INVALID"):
        module._runtime_contract(runtime)
