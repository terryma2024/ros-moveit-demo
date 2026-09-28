"""Task 11A: the collection boundary across a real process, not a mock.

The campaign runs in a child interpreter, so this test exercises what a mock cannot: that the package
imports where it will actually run, that a refusal reaches the parent as a non-zero exit with the reason on
stderr, and that the results on disk are the ones the child reported.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

_CHILD = '''
import json, sys
from pathlib import Path

from so101_demo.act.parallel_collection import FixedActCollectionCampaign

root = Path(sys.argv[1])
manifest = json.loads((root / "manifest.json").read_text())


class Port:
    def collect(self, scene_id, context, wave):
        return {"scene_id": scene_id, "status": "PASSED", "qc": "PASS", "done": True,
                "interventions": 0, "coordinator_committed": True, "reset_epoch": 1}


class Claim:
    def __init__(self):
        self.released = []

    def release(self, document):
        self.released.append(document)


claim = Claim()
campaign = FixedActCollectionCampaign(manifest, {"max_wave_size": 2, "qualification": False},
                                      context=None, root=root, collect_port=Port(), claim=claim)
outcome = campaign.run()
print(json.dumps({"scene_count": outcome["scene_count"], "collected": outcome["collected"],
                  "released": len(claim.released), "index": outcome["campaign_index"]}))
'''


def _child_environment():
    """The child inherits this interpreter's environment, so it imports the same installed package."""

    import os

    return {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def test_the_campaign_runs_in_a_child_process_and_reports_what_it_wrote(tmp_path):
    scenes = [{"scene_id": f"act-{index}", "split": "train"} for index in range(4)]
    (tmp_path / "manifest.json").write_text(json.dumps(
        {"kind": "W8", "scenarios": scenes,
         "qualification_contract": {"revoked": False, "scenes": 40}}))
    script = tmp_path / "child.py"
    script.write_text(_CHILD)
    completed = subprocess.run([sys.executable, str(script), str(tmp_path)],
                               capture_output=True, text=True, timeout=120,
                               env=_child_environment())
    assert completed.returncode == 0, completed.stderr
    reported = json.loads(completed.stdout.strip().splitlines()[-1])
    assert reported["scene_count"] == 4 and reported["released"] == 1
    assert Path(reported["index"]).is_file()
    index = json.loads(Path(reported["index"]).read_text())
    assert index["scene_count"] == 4
    assert [len(wave["scene_ids"]) for wave in index["waves"]] == [2, 2]
    for scene in scenes:
        result = json.loads((tmp_path / "results" / f"{scene['scene_id']}.json").read_text())
        assert result["status"] == "PASSED"


def test_a_refusal_reaches_the_parent_as_a_non_zero_exit_with_its_reason(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"kind": "W8"}))   # no scenarios at all
    script = tmp_path / "child.py"
    script.write_text(_CHILD)
    completed = subprocess.run([sys.executable, str(script), str(tmp_path)],
                               capture_output=True, text=True, timeout=120,
                               env=_child_environment())
    assert completed.returncode != 0
    assert "CAMPAIGN_MANIFEST_INVALID" in completed.stderr
    assert not (tmp_path / "campaign-index.json").exists()      # the refusal left nothing behind
