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
