"""The retired measurement entry point: it reports retirement and measures nothing.

Task 6 of the lightweight start guard plan. The certified measurement runtime is deleted;
the console entry stays registered so an operator who still types it gets an explicit
retirement error instead of a silently different mode.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

RETIRED_MODULES = (
    "so101_demo.parallel_batch.resource_budget",
    "so101_demo.parallel_batch.resource_measurement",
    "so101_demo.parallel_batch.measurement_control",
    "so101_demo.parallel_batch.owned_resources",
)

PACKAGE = Path(__file__).resolve().parents[1]
SOURCE = PACKAGE / "src"


def test_the_measurement_runtime_is_deleted_from_the_tree():
    for module in RETIRED_MODULES:
        relative = Path(*module.split(".")[1:]).with_suffix(".py")
        assert not (SOURCE / relative).exists(), module


def test_measurement_entry_is_retired():
    from so101_demo.cli import measure_parallel_resources as entry

    exit_code = entry.main(["--config", "/nonexistent/config.yaml", "--batch-id", "x"])
    assert exit_code == 2
    assert os.environ.get("SO101_MEASUREMENT_RETIRED_REASON") is None


def test_measurement_entry_reports_retirement_and_never_measures(capsys):
    from so101_demo.cli import measure_parallel_resources as entry

    exit_code = entry.main(["--help"]) if False else entry.main([])
    captured = capsys.readouterr()
    payload = json.loads((captured.out + captured.err).strip().splitlines()[-1])
    assert exit_code == 2
    assert payload["error"] == "MEASUREMENT_ENTRY_RETIRED"
    assert payload["authorizes_execution"] is False


def test_retired_console_script_is_still_registered_but_imports_no_budget_module():
    setup_py = (PACKAGE / "setup.py").read_text()
    assert "so101_measure_parallel_resources" in setup_py

    script = (
        "import json, sys\n"
        "RETIRED = " + repr(RETIRED_MODULES) + "\n"
        "class Trap:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name in RETIRED:\n"
        "            raise AssertionError('retired module imported: ' + name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Trap())\n"
        "from so101_demo.cli import measure_parallel_resources as entry\n"
        "entry.main([])\n"
        "print(json.dumps(sorted(n for n in sys.modules if 'parallel_batch' in n)))\n"
    )
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                               env=dict(os.environ))
    assert completed.returncode == 0, completed.stderr
    modules = json.loads(completed.stdout.strip().splitlines()[-1])
    for retired in RETIRED_MODULES:
        assert retired not in modules, modules
