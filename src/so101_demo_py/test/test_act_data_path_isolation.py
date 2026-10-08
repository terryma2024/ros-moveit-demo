"""No data path holds a reference to the Teacher's control objects, and no Teacher module reaches the data path (A4c).

Three independent proofs, because each can fail alone: the source (AST over every import and every named object), the
interpreter (a fresh process that imports the data path and finds no Teacher control module loaded), and the object graph
(what a prepared Recorder actually holds). The Recorder is a consumer of the Teacher's published facts and of the shared
physical sources; it is never given, and never imports, anything that can command.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parents[1] / "src"

#: every module that belongs to the data path of a recording
DATA_PATH = (
    "act/offline/engine.py", "act/offline/policy.py", "act/recorder_scene.py", "act/scene_operation.py",
    "act/episode_open.py", "act/collection_orchestration.py", "act/collection_reference.py",
    "act/frozen_runtime_inputs.py", "act/teacher_event_stream.py", "act/offline/sources.py",
    "ros/recorder_data_side.py", "ros/data_source_binding.py", "adapters/act/ros_teacher_event_stream.py",
    "adapters/act/ros_episode_physics.py", "adapters/act/ros_observation.py", "adapters/act/scene_state.py")

#: the Teacher's execution and control modules: none may be imported by the data path

#: names that denote a control object; a data-path module that names one holds a reference to it
CONTROL_NAMES = {
    "LeasedActionClient", "LeasedTeacherPhasePort", "LeasedCollectionReferencePort", "RosDynamicMujocoExecution",
    "context_from_environment", "connection_for", "_collection_port", "_teacher_phase_port", "ControllerReservationClient",
    "BrokerCommandConnection", "CommandBroker"}

#: the data path's own modules: no Teacher module may import them
#: (`ros.data_source_binding` and `act.frozen_runtime_inputs` are shared on purpose: the Teacher binds its own scene-state
#: observer through the former and loads its frozen snapshot through the latter.)
RECORDER_MODULES = {
    "so101_demo.ros.recorder_data_side", "so101_demo.act.offline.sources",
    "so101_demo.act.offline.engine", "so101_demo.act.offline.policy", "so101_demo.act.recorder_scene",
    "so101_demo.act.episode_open", "so101_demo.act.collection_orchestration"}


def imported_modules(path: Path) -> set[str]:
    """Every module the file can import, relative imports resolved, function-level imports included."""
    package = ("so101_demo." + ".".join(path.relative_to(SRC).parts[:-1])).rstrip(".")
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[:len(base) - node.level + 1]
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            names.add(module)
            names.update(module + "." + alias.name for alias in node.names)
    return names


@pytest.mark.parametrize("module", DATA_PATH)
def test_a_data_path_module_names_no_control_object(module):
    tree = ast.parse((SRC / module).read_text())
    named = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    named |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    named |= {alias.name.split(".")[-1] for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
              for alias in node.names}
    assert sorted(named & CONTROL_NAMES) == []


def reachable_class_names(root, *, limit=4000):
    """The class names of every object reachable from `root` through instance attributes, containers and closures."""
    seen, names, queue = set(), set(), [root]
    while queue and len(seen) < limit:
        value = queue.pop()
        if id(value) in seen or isinstance(value, (str, bytes, int, float, bool, type(None))):
            continue
        seen.add(id(value))
        names.add(type(value).__name__)
        if isinstance(value, dict):
            queue.extend(list(value.keys()) + list(value.values()))
        elif isinstance(value, (list, tuple, set, frozenset)):
            queue.extend(value)
        elif callable(value) and getattr(value, "__closure__", None):
            queue.extend(cell.cell_contents for cell in value.__closure__ if _filled(cell))
        elif hasattr(value, "__dict__") and not isinstance(value, type):
            queue.extend(vars(value).values())
    return names


def _filled(cell):
    try:
        cell.cell_contents
    except ValueError:
        return False
    return True


def test_a_prepared_recorder_holds_no_control_object_in_its_object_graph():
    from test_act_episode_recorder_sources import _prepared
    sources, node, engine, latched = _prepared()
    names = reachable_class_names(sources)
    assert "RecorderDataSide" in names and "OfflineRosSources" in names
    assert sorted(names & CONTROL_NAMES) == []
    assert not [call for call in node.calls if call[0] == "FORBIDDEN"], "the node was only ever asked to subscribe"


