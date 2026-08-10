import hashlib
import json
from pathlib import Path


PACKAGE = Path(__file__).parents[1]

def _live_source_path(recorded_source: str) -> Path:
    source = Path(recorded_source)
    if source.parts[:2] == ("src", "so101_gazebo_demo"):
        source = Path("src", "so101_gazebo_demo_cpp", *source.parts[2:])
    return PACKAGE.parents[1] / source


def test_provenance_has_exact_reference_and_hashes() -> None:
    payload = json.loads((PACKAGE / "docs/provenance.json").read_text())
    assert payload["reference_head"] == "05dff7a18e466c01486441dd90c21fcd44d4d8cd"
    assert payload["reference_branch"] == "main"
    assert payload["files"]
    for entry in payload["files"]:
        assert set(entry) == {
            "source", "destination", "source_dirty",
            "source_sha256", "destination_sha256",
        }
        assert len(entry["source_sha256"]) == 64
        assert len(entry["destination_sha256"]) == 64
        assert _live_source_path(entry["source"]).is_file()
        destination = PACKAGE / entry["destination"]
        assert destination.is_file()
        assert hashlib.sha256(destination.read_bytes()).hexdigest() == entry["destination_sha256"]
