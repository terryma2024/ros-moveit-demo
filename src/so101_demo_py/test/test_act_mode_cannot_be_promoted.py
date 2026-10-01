"""E2's negative list: a frozen diagnostic set cannot be run as a formal episode."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from so101_demo.cli.act_first_episode import main


def test_a_diagnostic_frozen_set_cannot_be_run_as_formal(tmp_path, capsys):
    """The mode is frozen with the inputs: asking for a different one is refused, and the refusal says which."""

    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "inputs-manifest.json").write_text(
        json.dumps({"mode": "preselected_target_diagnostic", "inputs_sha256": "a" * 64}))
    rc = main(["run", "--inputs", str(inputs), "--root", str(tmp_path / "run"), "--mode", "formal",
               "--final-cup-pose", "0,0,0,0,0,0,1"])
    captured = capsys.readouterr()
    print("MODE rc:", rc, "| stderr:", captured.err.strip()[:120])
    assert rc == 2
    assert "preselected_target_diagnostic" in captured.err      # it names the mode the set was prepared for
    assert "formal" in captured.err                             # and the one that was asked for
    assert not (tmp_path / "run").exists()                      # and nothing was created on the way to refusing
