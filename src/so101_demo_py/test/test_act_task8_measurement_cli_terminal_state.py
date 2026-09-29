"""The measurement entry's TERMINAL ledger state: a refused seal must leave INVALID, not RUNNING.

The independent review's P2 finding is that the seal validation sits OUTSIDE the handler that appends INVALID
(CP-1616): everything after the driver is unguarded, so a seal that fails `validate_closed_batch`, or a `batch.json`
that cannot be read, propagates while the ledger keeps saying `RUNNING`. Anything that reads the ledger - an operator, a
qualification report - then sees a run that never finished with no indication that it failed.

These cases use the entry's own `--driver` seam, so they need no live stack, no simulator and no hardware, and each of
them asserts the LEDGER, which is the artefact the finding is about. The existing suite asserts that such runs are
refused; what it never asserted is what the ledger says afterwards.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_act_task8_measurement_contract import _bound_contract  # noqa: E402


def _run(tmp_path, monkeypatch, *, driver_source, extra_document=None):
    """Drive the entry through its own seam and return (raised, ledger text)."""

    from so101_demo.cli import act_measure_task8_calibration as measure

    contract_path, identities_path = _bound_contract(tmp_path)
    driver_dir = tmp_path / "drivers"
    driver_dir.mkdir()
    (driver_dir / "seal_driver.py").write_text(driver_source)
    monkeypatch.syspath_prepend(str(driver_dir))
    ledger = tmp_path / "ledger.md"
    argv = ["--contract", str(contract_path), "--identities", str(identities_path),
            "--batch-root", str(tmp_path / "batch"), "--ledger", str(ledger),
            "--driver", "seal_driver:run"]
    if extra_document is not None:
        context_path = tmp_path / "context.json"
        context_path.write_text(json.dumps(extra_document))
        argv += ["--context", str(context_path)]
    raised = None
    try:
        measure.main(argv)
    except BaseException as error:                     # noqa: BLE001 - the refusal is the point
        raised = error
    return raised, (ledger.read_text() if ledger.is_file() else "")


def test_a_driver_that_seals_nothing_leaves_the_ledger_saying_invalid(tmp_path, monkeypatch):
    """The case the review named: the run is refused, so the ledger must not be left saying RUNNING."""

    raised, ledger = _run(tmp_path, monkeypatch, driver_source=(
        "from pathlib import Path\n"
        "def run(contract, batch_root):\n"
        "    root = Path(batch_root)\n"
        "    root.mkdir(parents=True, exist_ok=True)\n"
        "    (root / 'raw.json').write_text('{\"row\": 1}')\n"))
    assert raised is not None, "a driver that sealed nothing must be refused"
    assert "INVALID" in ledger, f"the ledger must record the terminal failure, got:\n{ledger}"
    assert "measurement VALID" not in ledger, ledger   # "VALID" is a substring of "INVALID"


def test_a_corrupted_seal_leaves_the_ledger_saying_invalid(tmp_path, monkeypatch):
    """A batch document that cannot pass the seal validator is a failed measurement, not an unfinished one."""

    raised, ledger = _run(tmp_path, monkeypatch, driver_source=(
        "import json\n"
        "from pathlib import Path\n"
        "def run(contract, batch_root):\n"
        "    root = Path(batch_root)\n"
        "    root.mkdir(parents=True, exist_ok=True)\n"
        "    (root / 'batch.json').write_text(json.dumps({'status': 'CLOSED', 'kind': 'not_the_right_kind'}))\n"))
    assert raised is not None, "a corrupted seal must be refused"
    assert "INVALID" in ledger, f"the ledger must record the terminal failure, got:\n{ledger}"
    assert "measurement VALID" not in ledger, ledger   # "VALID" is a substring of "INVALID"


# The driver below builds its own seal document, so these cases depend on neither the helper's shape nor the pending
# question about where the cleanup proof is required - they exercise the ENTRY's behaviour, which is what item 4 is
# about. The identity it seals with is the one its own run admitted unless the case says otherwise.
_SEAL_DRIVER = '''
import hashlib, json
from pathlib import Path

def _canonical(value):
    from so101_demo.act.task8_measurement_contract import _canonical as canonical
    return canonical(value)

def run(contract, batch_root, *, identity_override=None, contamination=None, with_cleanup=True):
    root = Path(batch_root); root.mkdir(parents=True, exist_ok=True)
    payload = b'{"row": 1}'
    (root / "raw.json").write_bytes(payload)
    identity = dict(identity_override) if identity_override else dict(contract["identities"])
    document = {
        "schema_version": 1, "kind": "act_task8_measurement_batch", "status": "CLOSED",
        "identity": identity,
        "files": {"raw.json": hashlib.sha256(payload).hexdigest()},
        "anchors": ["default", "left", "forward"],
    }
    if with_cleanup:
        document["cleanup"] = {"cleanup_complete": True}
    if contamination is not None:
        document["contamination"] = contamination
    document["batch_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()
    (root / "batch.json").write_text(json.dumps(document))

def run_contaminated(contract, batch_root):
    run(contract, batch_root, contamination="DEBRIS_LEFT_BEHIND")

def run_foreign_identity(contract, batch_root):
    foreign = {name: "c" * 64 for name in contract["identities"]}
    foreign["source_commit"] = "1" * 40
    run(contract, batch_root, identity_override=foreign)
'''


def _seal_run(tmp_path, monkeypatch, entry_point):
    from so101_demo.cli import act_measure_task8_calibration as measure

    contract_path, identities_path = _bound_contract(tmp_path)
    driver_dir = tmp_path / "drivers"
    driver_dir.mkdir()
    (driver_dir / "sealing_driver.py").write_text(_SEAL_DRIVER)
    monkeypatch.syspath_prepend(str(driver_dir))
    ledger = tmp_path / "ledger.md"
    raised = None
    try:
        measure.main(["--contract", str(contract_path), "--identities", str(identities_path),
                      "--batch-root", str(tmp_path / "batch"), "--ledger", str(ledger),
                      "--driver", f"sealing_driver:{entry_point}"])
    except BaseException as error:                     # noqa: BLE001
        raised = error
    return raised, (ledger.read_text() if ledger.is_file() else "")


def test_a_contaminated_seal_leaves_the_ledger_saying_invalid(tmp_path, monkeypatch):
    """Cleanup contamination: the batch keeps its evidence but must never be called a success."""

    raised, ledger = _seal_run(tmp_path, monkeypatch, "run_contaminated")
    assert raised is not None, "a contaminated batch must be refused"
    assert "measurement INVALID" in ledger, ledger
    assert "measurement VALID" not in ledger, ledger


def test_a_seal_belonging_to_another_identity_leaves_the_ledger_saying_invalid(tmp_path, monkeypatch):
    """A seal that validates in shape but belongs to another contract is not this run's evidence."""

    raised, ledger = _seal_run(tmp_path, monkeypatch, "run_foreign_identity")
    # WHICH layer refuses is an implementation detail - the schema's validator knows the contract's identity and the
    # entry now compares it too - so this asserts the BEHAVIOUR the review asked for: refused, and INVALID in the ledger
    assert raised is not None, "a seal whose identity differs from the admitted one must be refused"
    assert "measurement INVALID" in ledger, ledger
    assert "measurement VALID" not in ledger, ledger


def test_the_entry_exits_non_zero_when_its_seal_is_refused(tmp_path):
    """The fifth scenario: what an operator's shell sees, not only what the ledger says.

    Asserted as a PROCESS, the way the CLI-gate suite asserts the other entries: the entry is run with the same
    `raise SystemExit(main())` a script uses, and a refused seal must produce a non-zero status - otherwise a
    qualification script that checks exit codes would accept a failed measurement.
    """

    import subprocess

    contract_path, identities_path = _bound_contract(tmp_path)
    driver_dir = tmp_path / "drivers"
    driver_dir.mkdir()
    (driver_dir / "seal_driver.py").write_text(
        "from pathlib import Path\n"
        "def run(contract, batch_root):\n"
        "    root = Path(batch_root); root.mkdir(parents=True, exist_ok=True)\n"
        "    (root / 'raw.json').write_text('{\"row\": 1}')\n")
    ledger = tmp_path / "ledger.md"
    program = (
        "import sys;"
        "from so101_demo.cli.act_measure_task8_calibration import main;"
        "raise SystemExit(main(sys.argv[1:]))"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(driver_dir), env.get("PYTHONPATH", "")])
    done = subprocess.run(
        [sys.executable, "-c", program,
         "--contract", str(contract_path), "--identities", str(identities_path),
         "--batch-root", str(tmp_path / "batch"), "--ledger", str(ledger),
         "--driver", "seal_driver:run"],
        capture_output=True, text=True, timeout=120, env=env)
    assert done.returncode != 0, f"a refused seal must exit non-zero, got {done.returncode}"
    assert "measurement INVALID" in ledger.read_text(), ledger.read_text()
