"""Ordinary-gate tests must not depend on files under /data/work or /opt/data/work (another machine has neither).

A test that needs data builds it under ``tmp_path`` or reads a vendored file below the package's ``test/data``,
resolved relative to ``__file__``. Large artefacts (weights, evidence trees) are never vendored: use a small synthetic
stand-in, or mark the test as an integration test outside the ordinary gate.

The allowlist holds only path *strings* that are inputs to validation logic and are never opened; every entry says why.
"""
from paths import REPOSITORY

TEST_TREES = (
    "src/so101_demo_py/test",
    "src/so101_teleop/test",
    "src/so101_mujoco_support/test",
    "third_party/mujoco_ros2_control/mujoco_ros2_control/tests",
    "third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/test",
    "third_party/mujoco_ros2_control/mujoco_ros2_control_tests/test",
)
LITERALS = ("/data/work", "/opt/data/work")
SUFFIXES = {".py", ".json", ".yaml", ".yml", ".txt", ".md", ".cpp", ".hpp", ".zsh", ".sh", ".xml", ".toml", ".cfg"}
SELF = "src/so101_demo_py/test/repo/test_no_host_paths_in_tests.py"

ALLOWED = {
    # an evidence_root string inside a receipt/document fixture; the validators only check it is a non-empty string
    "src/so101_demo_py/test/act/test_act_contact_policy_activation.py": "receipt field string, never opened",
    "src/so101_demo_py/test/act/test_act_pick_place_calibration_admission.py": "document field string, never opened",
    "src/so101_demo_py/test/act/test_act_pick_place_validation_formal_context_fields.py": "document field string, never opened",
    "src/so101_demo_py/test/act/test_act_pick_place_calibration_measurement_driver.py": "document field string, never opened",
    "src/so101_demo_py/test/act/test_act_pick_place_validation_campaign.py": "document field string, never opened",
    "src/so101_teleop/test/unified/test_act_campaign_admission.py": "document field string, never opened",
    # the AF_UNIX 107-byte boundary is a property of the path string length; nothing is created
    "src/so101_demo_py/test/parallel_batch/test_parallel_adaptive_pool.py": "socket path length arithmetic on strings",
    "src/so101_demo_py/test/repo/test_pytest_full_gate_runner.py": "socket path budget arithmetic on strings",
    "src/so101_demo_py/test/cli/test_parallel_batch_cli_composition.py": "string argument compared with the CLI's own output",
    "src/so101_demo_py/test/ports/test_pick_place_executor_adapter.py": "installed_prefix label passed to a fake adapter",
    # command-line arguments for argument-parsing / option-binding tests
    "src/so101_demo_py/test/application/test_qualification_runner.py": "CLI argument string; the runner is parsed, not executed",
    "src/so101_demo_py/test/cli/test_teleop_owner.py": "checkpoint path argument of an argument builder",
    # window-title / process-command-line / platform-rule classifiers on strings
    "src/so101_teleop/test/test_ai_station_x11.py": "window title string for a classifier",
    "src/so101_teleop/test/test_tile_ai_station_guis.py": "window title string for a classifier",
    "src/so101_teleop/test/test_so101_stack_inventory.py": "process command line for a parser",
    "src/so101_teleop/test/test_unified_gate.py": "durable-root rule inputs (platform, path) for a pure predicate",
    "src/so101_teleop/test/unified/test_unified_live_fixture.py": "asserts the literal appears in a tracked TypeScript rule file",
    # not collected by pytest: the recorded-gate helper keeps the registered-host policy constant
    "src/so101_teleop/test/e2e/record_gate.py": "registered-host policy constant for a pure predicate",
}


def _files():
    for tree in TEST_TREES:
        root = REPOSITORY / tree
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if (path.is_file() and path.suffix in SUFFIXES and "node_modules" not in path.parts
                    and "__pycache__" not in path.parts):
                yield path


def test_no_test_or_fixture_names_a_host_specific_data_path_outside_the_allowlist():
    offenders = {}
    for path in _files():
        relative = path.relative_to(REPOSITORY).as_posix()
        if relative == SELF:
            continue
        text = path.read_text(errors="ignore")
        if any(literal in text for literal in LITERALS) and relative not in ALLOWED:
            offenders[relative] = [line.strip()[:120] for line in text.splitlines()
                                   if any(literal in line for literal in LITERALS)][:3]
    assert not offenders, (
        "tests must build their data under tmp_path or read vendored test/data files; "
        f"host paths found: {offenders}")


def test_every_allowlist_entry_still_has_a_literal():
    stale = [name for name in ALLOWED
             if not (REPOSITORY / name).is_file()
             or not any(literal in (REPOSITORY / name).read_text(errors="ignore") for literal in LITERALS)]
    assert not stale, f"drop allowlist entries that no longer need it: {stale}"
