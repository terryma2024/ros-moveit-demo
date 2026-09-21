from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TARGET = PACKAGE_ROOT / "test/test_sam_decoder_runtime.py"
EXPLICIT_ML_CASES = {
    "test/test_sam_decoder_runtime.py::"
    "test_epoch_export_binds_model_optimizer_receipt_and_identity",
    "test/test_sam_decoder_runtime.py::test_export_failure_never_marks_checkpoint_complete",
    "test/test_sam_decoder_runtime.py::test_real_processor_accepts_two_jittered_box_prompts",
}


def _collected(*selection: str) -> set[str]:
    environment = dict(os.environ)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(TARGET),
            "--collect-only",
            "-q",
            *selection,
        ],
        cwd=PACKAGE_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return {
        line.removeprefix(str(PACKAGE_ROOT) + "/")
        for line in completed.stdout.splitlines()
        if "::" in line
    }


def test_default_collection_excludes_explicit_ml_cases() -> None:
    collected = _collected()

    assert collected.isdisjoint(EXPLICIT_ML_CASES)
    assert (
        "test/test_sam_decoder_runtime.py::"
        "test_training_rejects_invalid_source_before_creating_output"
        in collected
    )


def test_explicit_ml_marker_collects_only_opt_in_cases() -> None:
    assert _collected("-m", "explicit_ml") == EXPLICIT_ML_CASES
