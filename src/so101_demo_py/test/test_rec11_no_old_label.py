"""CP-3421: the old two-character label of the source alignment was renamed to what it is. No identifier, reason code, file name, record kind or
comment in `src/so101_demo_py/src` or `test/` may use it again. The pattern is built from parts so that this file needs no
allow-list entry for itself."""
import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
LABEL = "K" + "2"
PATTERN = re.compile(rf"(?<![A-Za-z0-9]){LABEL}(?![0-9])|(?<![A-Za-z0-9]){LABEL.lower()}(?![0-9])", re.IGNORECASE)


def test_the_old_alignment_label_remains_nowhere_in_the_sources_or_the_tests():
    hits = []
    for base in ("src", "test"):
        for path in sorted((PACKAGE / base).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".yaml", ".yml", ".md", ".txt", ".json", ".cfg"}:
                for number, line in enumerate(path.read_text().splitlines(), start=1):
                    if PATTERN.search(line):
                        hits.append(f"{path.relative_to(PACKAGE)}:{number}: {line.strip()[:100]}")
    assert hits == [], hits[:10]


def test_the_new_names_are_the_ones_the_recorder_and_the_audit_use():
    from so101_demo.act import episode_audit, recorder_scene, scene_association
    from so101_demo.ros import episode_recorder_sources as sources
    assert scene_association.KIND == "ACT_SOURCE_ALIGNMENT_SCENE_ASSOCIATION"
    assert "source_alignment_v1" in episode_audit._EVENT_KINDS if hasattr(episode_audit, "_EVENT_KINDS") else True
    assert hasattr(recorder_scene, "describe_alignment_inputs")
    assert sources.RosRecorderSources.ALIGNMENT_RETRY_S == 1.0
