"""The reservation, witness and broker stack is gone: the import graph, the files and the plugin list.

Names are built from fragments so a repository-wide absence search over the deleted stems stays meaningful.
The Head neck is the stock joint trajectory controller plus a thin subclass (design 2026-10-10); nothing may
import, build or declare what the broker era needed.
"""
import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
REPOSITORY = PACKAGE.parents[1]
SUPPORT = REPOSITORY / "src/so101_mujoco_support"
TELEOP = REPOSITORY / "src/so101_teleop/so101_teleop"


def _name(*parts):
    return "_".join(parts)


#: the Python modules that carried the reservation protocol, the native close and the broker port
DELETED_PYTHON = {
    "so101_demo.adapters.act." + _name("controller", "reservation", "client"),
    "so101_demo.adapters.act." + _name("controller", "reservation", "provision"),
    "so101_demo.adapters.act." + _name("head", "execution", "native"),
    "so101_demo.adapters.act." + _name("head", "reservation", "authority"),
    "so101_demo.adapters.act." + _name("head", "revocation"),
    "so101_demo.adapters.act." + _name("head", "native", "policy", "readback"),
    "so101_demo.adapters.act." + _name("broker", "execution"),
    "so101_demo.adapters.act." + _name("head", "control", "protocol"),
    "so101_teleop.unified." + _name("controller", "reservation", "paths"),
}

DELETED_PYTHON_FILES = [
    PACKAGE / "src/adapters/act" / (_name("controller", "reservation", "client") + ".py"),
    PACKAGE / "src/adapters/act" / (_name("controller", "reservation", "provision") + ".py"),
    PACKAGE / "src/adapters/act" / (_name("head", "execution", "native") + ".py"),
    PACKAGE / "src/adapters/act" / (_name("head", "reservation", "authority") + ".py"),
    PACKAGE / "src/adapters/act" / (_name("head", "revocation") + ".py"),
    PACKAGE / "src/adapters/act" / (_name("head", "native", "policy", "readback") + ".py"),
    PACKAGE / "src/adapters/act" / (_name("broker", "execution") + ".py"),
    PACKAGE / "src/adapters/act" / (_name("head", "control", "protocol") + ".py"),
    TELEOP / "unified" / (_name("controller", "reservation", "paths") + ".py"),
]

DELETED_NATIVE = [
    "include/so101_mujoco_support/" + name for name in (
        "bound_reservation.hpp", "broker_owned_trajectory_controller.hpp", "controller_goal_admission.hpp",
        "controller_goal_types.hpp", "controller_ingress_witness.hpp", "controller_reservation_protocol.hpp",
        "controller_reservation_provision.hpp", "controller_reservation_role.hpp",
        "controller_reservation_socket.hpp", "controller_stop_evaluation.hpp", "controller_stop_witness.hpp",
        "head_revocation_transport.h", "sha256.hpp", "stop_timing_collector.hpp")
] + [
    "src/" + name for name in (
        "broker_owned_trajectory_controller.cpp", "controller_reservation_protocol.cpp",
        "controller_reservation_provision.cpp", "controller_reservation_socket.cpp",
        "head_revocation_transport.cpp")
] + [
    "test/" + name for name in (
        "controller_reservation_provision_writer.py", "controller_stop_witness_test_access.hpp",
        "stop_witness_timing_stress.cpp", "test_broker_owned_trajectory_controller.cpp",
        "test_controller_goal_admission.cpp", "test_controller_ingress_witness.cpp",
        "test_controller_reservation_protocol.cpp", "test_controller_reservation_provision.cpp",
        "test_controller_stop_witness.cpp", "test_controller_stop_witness_stress.cpp",
        "test_gate6_bound_admission_state.cpp", "test_gate6_bound_reservation_frame.cpp",
        "test_gate6_bound_socket.cpp", "test_gate6_lifecycle.cpp", "test_gate6_service_identity.cpp",
        "test_gate6_sha256_vectors.cpp", "test_head_revocation_transport.cpp",
        "fixtures/bound_frame_v2.bin", "fixtures/bound_frame_v2.json",
        "fixtures/head_neck_bound_frame_v2.bin")
]


def _imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _python_sources():
    roots = [PACKAGE / "src", PACKAGE / "test", TELEOP.parent]
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts or path.name == Path(__file__).name:
                continue
            yield path


def test_no_python_module_imports_a_deleted_reservation_module():
    offenders = {}
    for path in _python_sources():
        bad = sorted(_imported_modules(path) & DELETED_PYTHON)
        if bad:
            offenders[str(path.relative_to(REPOSITORY))] = bad
    assert not offenders, offenders


@pytest.mark.parametrize("path", DELETED_PYTHON_FILES, ids=lambda path: path.name)
def test_a_deleted_python_module_has_no_file(path):
    assert not path.exists()


@pytest.mark.parametrize("name", DELETED_NATIVE)
def test_a_deleted_native_file_is_gone(name):
    assert not (SUPPORT / name).exists()


def test_the_native_build_and_plugin_list_declare_only_the_head_neck_controller():
    cmake = (SUPPORT / "CMakeLists.txt").read_text()
    plugins = (SUPPORT / "so101_trajectory_controllers.xml").read_text()
    for stem in (_name("broker", "owned"), _name("controller", "reservation"), _name("head", "revocation"),
                 _name("stop", "witness"), _name("gate6"), _name("ingress", "witness"),
                 _name("controller", "goal", "admission")):
        assert stem not in cmake, stem
    assert _name("broker", "owned") not in plugins and "BrokerOwned" not in plugins
    assert "HeadNeckTrajectoryController" in plugins
    assert "so101_head_neck_trajectory_controller" in cmake and "test_head_neck_deadman" in cmake


def test_the_head_neck_limits_module_no_longer_pins_a_broker_source():
    text = (PACKAGE / "test/test_act_head_neck_limits.py").read_text()
    assert _name("broker", "owned", "trajectory", "controller") not in text
