"""CP-3459: every child role runs the qualified install's code.

Live L1 and L2 on freeze feAWPg9k failed before the Teacher with `SupervisorError: EARLY_EXIT: broker: 1`. The broker is the
image `so101-parallel-perception:...-v1` started by `docker run`; its `/opt/venv/bin/so101_parallel_perception_broker` imported the
`so101_demo` baked into the image on 2026-09-24 (source tree 3624dac7...), not the qualified install, and that older parser refused
the ACT runtime config (`FROZEN_RUNTIME_VALUE: lease_duration_s`). It was not a PATH lookup on the host: every live run has used the
baked broker code; it only mattered now that a config differs. The container now gets the qualified package mounted read-only over
the baked one, and every role command is resolved so that nothing is found by PATH.
"""

import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import so101_demo
from so101_demo.cli import parallel_perception_broker as broker_cli
from so101_demo.runtime import qualified_commands
from so101_demo.runtime.qualified_commands import QualifiedCommandError, qualified_prefix_from_env, resolve_role_command

from test_parallel_batch_cli import local_start_guard  # noqa: E402,F401  (the offline start-guard seam: an autouse fixture)

PACKAGE = Path(os.path.realpath(so101_demo.__file__)).parent
#: a prefix that contains the running package, standing for `<freeze>/qualified-install`
PREFIX = PACKAGE.parent


def _decoy_path(tmp_path, names=("so101_parallel_perception_broker", "docker", "ros2", "python3", "python")):
    bin_dir = tmp_path / "decoy-bin"
    bin_dir.mkdir()
    for name in names:
        path = bin_dir / name
        path.write_text("#!/bin/sh\nexit 97\n")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return bin_dir


# ---- the container gets the qualified package --------------------------------------------------------------------------------

def _container_kwargs(tmp_path):
    root = tmp_path / "batch"
    root.mkdir(mode=0o700)
    (root / "workers").mkdir(mode=0o700)
    yolo, grounded = tmp_path / "yolo", tmp_path / "grounded"
    yolo.mkdir()
    grounded.mkdir()
    (yolo / "best.pt").write_bytes(b"model")
    return root, dict(image_id="sha256:" + "b" * 64, yolo_weights=yolo / "best.pt", grounded_root=grounded, gpu_groups=[44],
                      uid=os.getuid(), gid=os.getgid(), batch_id="batch-1", broker_generation=1)


def test_the_container_mounts_the_qualified_package_read_only_over_the_baked_one(tmp_path):
    root, kwargs = _container_kwargs(tmp_path)
    argv = broker_cli.container_run_argv(root, source_package=PACKAGE, **kwargs)
    mount = f"{PACKAGE}:{broker_cli.IMAGE_PACKAGE_PATH}:ro"
    assert mount in argv and argv[argv.index(mount) - 1] == "--volume"
    assert argv.index(mount) < argv.index(kwargs["image_id"]), "the mount is a docker option, before the image"
    assert broker_cli.IMAGE_PACKAGE_PATH == "/opt/venv/lib/python3.12/site-packages/so101_demo"
    label = [item for item in argv if item.startswith("com.so101.source-sha256=")]
    assert label == ["com.so101.source-sha256=" + broker_cli.source_hash(PACKAGE)]


def test_without_a_source_package_the_container_argv_is_what_it_was(tmp_path):
    root, kwargs = _container_kwargs(tmp_path)
    argv = broker_cli.container_run_argv(root, **kwargs)
    assert not any(broker_cli.IMAGE_PACKAGE_PATH in item for item in argv)
    assert not any(item.startswith("com.so101.source-sha256=") for item in argv)


@pytest.mark.parametrize("fault", ["relative", "missing", "file", "symlink", "not_the_package"])
def test_a_source_package_that_is_not_the_package_is_refused(tmp_path, fault):
    root, kwargs = _container_kwargs(tmp_path)
    if fault == "relative":
        package = Path("so101_demo")
    elif fault == "missing":
        package = tmp_path / "absent"
    elif fault == "file":
        package = tmp_path / "file"
        package.write_text("x")
    elif fault == "symlink":
        package = tmp_path / "link"
        package.symlink_to(PACKAGE)
    else:
        package = tmp_path / "empty"
        package.mkdir()
    with pytest.raises(ValueError, match="QUALIFIED_PACKAGE_INVALID"):
        broker_cli.container_run_argv(root, source_package=package, **kwargs)


def test_the_qualified_package_root_is_the_running_package_and_must_lie_inside_the_install(tmp_path):
    assert broker_cli.qualified_package_root({}) == PACKAGE
    assert broker_cli.qualified_package_root({"SO101_QUALIFIED_FREEZE": str(PREFIX.parent)}) == PACKAGE if (
        PREFIX.parent / "qualified-install").resolve() == PREFIX else True
    elsewhere = tmp_path / "freeze"
    (elsewhere / "qualified-install").mkdir(parents=True)
    with pytest.raises(ValueError, match="QUALIFIED_PACKAGE_OUTSIDE_INSTALL"):
        broker_cli.qualified_package_root({"SO101_QUALIFIED_FREEZE": str(elsewhere)})


def test_the_composition_starts_the_broker_with_the_qualified_package(tmp_path, monkeypatch):
    """The default (container) route hands `container_run_argv` the package of the running install; outside the install it stops."""
    from test_parallel_batch_cli import argv as cli_argv, verified
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition, prepare_batch
    from so101_demo.parallel_batch.resources import ResourceSnapshot
    from so101_demo.parallel_batch.resources import runtime_ipc_base

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)

        def ros_domain_in_use(self, _domain):
            return False

        def socket_in_use(self, _path):
            return False

    class Supervisor:
        def __init__(self):
            self.started = []

        def start(self, role, command):
            self.started.append((role, tuple(command)))
            return SimpleNamespace(role=role)

    batch_id = "p3-role-provenance"
    monkeypatch.setenv("SO101_PARALLEL_IPC_BASE", str(runtime_ipc_base()))
    record = {**verified({}), "image_id": "sha256:" + "b" * 64}
    spec = prepare_batch(cli_argv(tmp_path / "batch", batch_id=batch_id, worker_count="1", point_id=("task_start",), run_mode="plan_only"),
                         provenance_verifier=lambda _value: record)
    captured = {}
    monkeypatch.setattr(broker_cli, "image_record", lambda _image: {"image_id": record["image_id"]})
    monkeypatch.setattr(broker_cli, "gpu_groups", lambda: [44])
    monkeypatch.setattr(broker_cli, "container_run_argv", lambda root, **kw: captured.update(kw) or ("docker", "run", "broker"))
    supervisor = Supervisor()
    composition = ProductionBatchComposition(spec, resource_probe=Probe(), claim_root=tmp_path / "claims", supervisor=supervisor)
    try:
        composition._start_broker()
        assert captured["source_package"] == PACKAGE and supervisor.started == [("broker", ("docker", "run", "broker"))]
        elsewhere = tmp_path / "freeze"
        (elsewhere / "qualified-install").mkdir(parents=True)
        monkeypatch.setenv("SO101_QUALIFIED_FREEZE", str(elsewhere))
        supervisor.started.clear()
        with pytest.raises(ValueError, match="QUALIFIED_PACKAGE_OUTSIDE_INSTALL"):
            composition._start_broker()
        assert supervisor.started == [], "no process was started"
    finally:
        composition._release_partial()
        assert composition._release_runtime_ipc_root() is True


# ---- no role is found by PATH ----------------------------------------------------------------------------------------------------

def test_every_role_command_resolves_to_a_qualified_executable_under_a_decoy_path(tmp_path, monkeypatch):
    from so101_demo.act.offline.orchestration import PROCESSOR_ROLE, RAW_ROLE
    from so101_demo.cli.act_first_episode import _broker_command
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition

    decoys = _decoy_path(tmp_path)
    monkeypatch.setenv("PATH", f"{decoys}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("ROS_DISTRO", "jazzy")
    composition = SimpleNamespace(runtime_ipc_root=tmp_path / "ipc", authority=SimpleNamespace(ipc_root=tmp_path / "ipc"),
                                  broker_input_root=tmp_path / "inputs", broker_runtime_root=tmp_path / "rt",
                                  broker_spec_path=tmp_path / "rt" / "broker-spec.json", spec=SimpleNamespace(yolo_weights=tmp_path / "y.pt"))
    commands = {
        "worker": ProductionBatchComposition.worker_command(tmp_path / "worker.json"),
        "broker-host-route": tuple(_broker_command(composition)),
        "broker-container-route": ("docker", "run", "--rm", "image"),
        "task-station": ("ros2", "launch", "so101_demo_py", "station.launch.py"),
        "dynamic-consumer": (sys.executable, "-m", "so101_demo.cli.dynamic_cup_pick_place", "--mode", "execute"),
        RAW_ROLE: (sys.executable, "-m", "so101_demo.act.offline.raw_recorder", "--bag-dir", "b"),
        PROCESSOR_ROLE: (sys.executable, "-m", "so101_demo.cli.act_offline_episode", "--bag", "b"),
    }
    for role, command in commands.items():
        resolved = resolve_role_command(command, prefix=PREFIX)
        assert Path(resolved[0]).is_absolute(), role
        assert not str(Path(resolved[0]).parent) == str(decoys), f"{role} was found in the decoy directory"
        assert "decoy-bin" not in " ".join(resolved), role
        if resolved[0] != command[0]:
            assert Path(resolved[0]).parent in (Path("/usr/local/bin"), Path("/usr/bin"), Path("/bin"), Path("/opt/ros/jazzy/bin")), role


def test_a_bare_so101_entry_point_is_refused_even_if_a_decoy_comes_first_on_the_path(tmp_path, monkeypatch):
    decoys = _decoy_path(tmp_path)
    monkeypatch.setenv("PATH", f"{decoys}:{os.environ.get('PATH', '')}")
    for command in (("so101_parallel_perception_broker", "--endpoint", "x"), (str(decoys / "so101_parallel_perception_broker"),),
                    ("/opt/venv/bin/so101_parallel_perception_broker",), ("python3", "-m", "so101_demo.cli.parallel_perception_broker"),
                    ("some-other-tool",)):
        with pytest.raises(QualifiedCommandError, match="ROLE_EXECUTABLE_(NOT|OUTSIDE)_QUALIFIED"):
            resolve_role_command(command, prefix=PREFIX)


def test_a_module_outside_the_install_and_a_console_script_outside_it_are_refused(tmp_path):
    other = tmp_path / "stale" / "site-packages"
    (other / "so101_demo").mkdir(parents=True)
    (other / "so101_demo" / "__init__.py").write_text("")
    with pytest.raises(QualifiedCommandError, match="ROLE_MODULE_OUTSIDE_QUALIFIED_INSTALL"):
        resolve_role_command((sys.executable, "-m", "so101_demo.cli.act_offline_episode"), prefix=tmp_path / "stale")
    script = tmp_path / "stale" / "bin" / "so101_parallel_perception_broker"
    script.parent.mkdir(parents=True)
    script.write_text("")
    with pytest.raises(QualifiedCommandError, match="ROLE_EXECUTABLE_OUTSIDE_QUALIFIED_INSTALL"):
        resolve_role_command((str(script),), prefix=PREFIX)
    inside = PREFIX / "bin" / "so101_x"
    assert resolve_role_command((str(inside),), prefix=PREFIX) == (str(inside),)


def test_without_a_prefix_the_checks_are_the_allow_list_only(monkeypatch):
    assert qualified_prefix_from_env({}) is None
    assert qualified_prefix_from_env({"SO101_QUALIFIED_FREEZE": "/f"}) == Path("/f/qualified-install")
    assert resolve_role_command((sys.executable, "-m", "so101_demo.cli.act_offline_episode"), prefix=None)[0] == sys.executable
    with pytest.raises(QualifiedCommandError, match="ROLE_EXECUTABLE_NOT_QUALIFIED"):
        resolve_role_command(("so101_parallel_perception_broker",), prefix=None)


def test_the_supervisor_resolves_before_it_starts_and_refuses_before_any_process(tmp_path):
    from so101_demo.runtime.parallel_processes import ProcessSupervisor, SupervisorError

    started = []

    class Child:
        pid = 0

        def poll(self):
            return 1

    def popen(argv, **kwargs):
        started.append(tuple(argv))
        return Child()

    supervisor = ProcessSupervisor("batch-1", popen=popen, qualified_prefix=PREFIX)
    with pytest.raises(SupervisorError, match="ROLE_EXECUTABLE_NOT_QUALIFIED"):
        supervisor.start("broker", ("so101_parallel_perception_broker", "--endpoint", "x"))
    assert started == [], "nothing was started"
    with pytest.raises(SupervisorError):
        supervisor.start("worker", (sys.executable, "-m", "so101_demo.cli.mujoco_parallel_batch", "--internal-worker", "x"))
    assert started and started[0][0] == sys.executable, "a qualified command reaches Popen (and fails later on the fake child)"
