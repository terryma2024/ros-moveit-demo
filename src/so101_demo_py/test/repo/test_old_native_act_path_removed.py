"""The old native ACT path is gone: `act_diagnostic_episode run`, its station, its launch file and the ACT fields of the native batch
worker specification. ACT collection runs through `act_collect_parallel` (container or `--instance-launcher native`).

What stays is named here as well, so a later cleanup cannot remove the read-only tooling the campaign and the historical runs use.
"""
import re

import pytest
from paths import PACKAGE_ROOT, REPOSITORY

PACKAGE = PACKAGE_ROOT
SOURCE = PACKAGE / "src"
TELEOP = REPOSITORY / "src/so101_teleop/so101_teleop"

REMOVED_FILES = (
    SOURCE / "cli/act_collect.py",
    SOURCE / "runtime/act_diagnostic_episode_station.py",
    PACKAGE / "launch/so101_mujoco_act.launch.py",
)

#: the names the removed code was reached by; built from fragments so this file does not match its own search
REMOVED_NAMES = (
    "act_diagnostic_" + "episode_station", "Diagnostic" + "EpisodeStation", "act_diagnostic_" + "episode_inputs",
    "act_expected_" + "inputs_sha256", "so101_mujoco_" + "act.launch", "_verified_" + "run_completion",
    "_nonhead_" + "provenance",
)


@pytest.mark.parametrize("path", REMOVED_FILES, ids=lambda path: path.name)
def test_removed_entry_point_files_are_absent(path):
    assert not path.exists()


def test_no_source_names_the_removed_entry_points():
    offenders = []
    roots = (SOURCE, PACKAGE / "launch", TELEOP)
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            text = path.read_text()
            offenders += [(str(path.relative_to(REPOSITORY)), name) for name in REMOVED_NAMES if name in text]
    assert offenders == []


def test_console_scripts_keep_the_read_only_tooling_and_drop_act_collect():
    setup = (PACKAGE / "setup.py").read_text()
    entries = set(re.findall(r'"([A-Za-z0-9_]+) = so101_demo\.', setup))
    assert "act_collect" not in entries
    assert {"act_collect_parallel", "act_diagnostic_episode"} <= entries


def test_act_diagnostic_episode_keeps_exactly_the_non_run_commands():
    from so101_demo.cli import act_diagnostic_episode

    parser = act_diagnostic_episode.build_parser()
    commands = next(action for action in parser._actions if getattr(action, "choices", None)).choices
    assert set(commands) == {"inspect", "prepare", "preflight", "qc", "verify-commit", "check-export", "readback"}
    with pytest.raises(SystemExit) as caught:
        parser.parse_args(["run", "--inputs", "i", "--root", "r"])
    assert caught.value.code == 2
    assert not hasattr(act_diagnostic_episode, "_run")


def test_the_native_batch_worker_specification_carries_no_act_fields():
    text = (SOURCE / "cli/mujoco_batch/worker_process.py").read_text() + (SOURCE / "cli/mujoco_batch/composition.py").read_text()
    for field in ("episode_scope_path", "episode_inputs_manifest", "collection_from_document"):
        assert field not in text, field
    # the campaign's artifact writer keeps its collection branch: it is what the container and native shards seal through
    assert "collection_scope" in (SOURCE / "cli/mujoco_batch/worker_process.py").read_text()


def test_the_station_hook_is_gone_from_the_worker_runtime():
    assert "DiagnosticEpisodeStation" not in (SOURCE / "runtime/parallel_worker_runtime.py").read_text()


def test_admission_no_longer_knows_the_diagnostic_episode_kind():
    text = (TELEOP / "unified/admission.py").read_text()
    assert "act_diagnostic_episode" not in text and "_DIAGNOSTIC" not in text
