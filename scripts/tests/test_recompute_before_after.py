"""The before/after recompute script of the mount-tree migration: two checkouts, one stand-in `recompute` each. No sealed run needed."""

import json
from pathlib import Path
import sys

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "migration"
sys.path.insert(0, str(SCRIPT_DIR))
import recompute_before_after as rba  # noqa: E402


def checkout(tmp_path, name, body):
    """A fake repository whose `so101_demo.act.collection_qualification_recompute` is `body`."""

    package = tmp_path / name / "src" / "so101_demo_py" / "src"
    (package / "act").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "act" / "__init__.py").write_text("")
    (package / "act" / "collection_qualification_recompute.py").write_text(
        "import json\n"
        "def canonical(document):\n    return json.dumps(document, sort_keys=True, separators=(',', ':')).encode() + b'\\n'\n" + body)
    return tmp_path / name


SAME = "def recompute(run_root, contract_path):\n    return {'status': 'PASSED', 'run': run_root.name, 'reasons': []}\n"
OTHER = "def recompute(run_root, contract_path):\n    return {'status': 'FAILED', 'run': run_root.name, 'reasons': ['X']}\n"
RAISES = "def recompute(run_root, contract_path):\n    raise ValueError('RUN_UNREADABLE')\n"


def roots(tmp_path, *labels):
    return {label: (str(tmp_path / label), str(tmp_path / (label + ".json"))) for label in labels}


def compare(tmp_path, before, after, *labels, **kwargs):
    kwargs.setdefault("require_modules", ())
    return rba.compare(roots(tmp_path, *labels), before, after, sys.executable, tmp_path / "out", **kwargs)


def argv_for(tmp_path, before, after, *labels, expect="PASSED", extra=()):
    argv = ["--before", str(before), "--after", str(after), "--out", str(tmp_path / "out"), "--require-module", "json",
            "--image-mode", labels[0], *extra]
    for label in labels:
        argv += ["--root", f"{label}={tmp_path / label}:{tmp_path / (label + '.json')}", "--expect", f"{label}={expect}"]
    return argv


def test_identical_reports_with_the_expected_verdict_on_every_root_pass(tmp_path):
    before, after = checkout(tmp_path, "before", SAME), checkout(tmp_path, "after", SAME)
    rows = compare(tmp_path, before, after, "image-mode", "mount", expected={"image-mode": "PASSED", "mount": "PASSED"})
    assert [row["same"] for row in rows] == [True, True] and all(row["usable"] for row in rows)
    assert rows[0]["before"] == rows[0]["after"] == "PASSED"
    saved = json.loads((tmp_path / "out" / "mount.before.json").read_text())
    assert saved["outcome"] == "REPORT" and '"run":"mount"' in saved["canonical"]


def test_a_changed_verdict_on_one_root_fails_the_command(tmp_path, capsys):
    before, after = checkout(tmp_path, "before", SAME), checkout(tmp_path, "after", OTHER)
    assert rba.main(argv_for(tmp_path, before, after, "image-mode")) == 1
    printed = capsys.readouterr().out
    assert "DIFFERENT  before=PASSED after=FAILED" in printed and "RESULT: FAIL" in printed


def test_the_same_refusal_before_and_after_is_a_failure_not_a_match(tmp_path):
    before, after = checkout(tmp_path, "before", RAISES), checkout(tmp_path, "after", RAISES)
    (row,) = compare(tmp_path, before, after, "r")
    assert row["same"] and not row["usable"] and row["before"] == "RAISED"
    (row,) = compare(tmp_path, before, tmp_path / "no-such-checkout", "r")
    assert row["same"] is False and row["after"] == "SETUP" and not row["usable"]


def test_a_report_with_another_verdict_than_the_recorded_one_fails_even_when_both_sides_agree(tmp_path):
    before, after = checkout(tmp_path, "before", OTHER), checkout(tmp_path, "after", OTHER)
    (row,) = compare(tmp_path, before, after, "r", expected={"r": "PASSED"})
    assert row["same"] and row["before"] == "FAILED" and not row["usable"]
    (row,) = compare(tmp_path, before, after, "r", expected={"r": "FAILED"})
    assert row["usable"]


def test_the_command_passes_only_when_every_root_agrees_and_prints_a_line_per_root(tmp_path, capsys):
    before, after = checkout(tmp_path, "before", SAME), checkout(tmp_path, "after", SAME)
    assert rba.main(argv_for(tmp_path, before, after, "image-mode", "mount")) == 0
    printed = capsys.readouterr().out
    assert printed.count("IDENTICAL") == 2 and "RESULT: PASS" in printed


def test_every_root_needs_an_expected_verdict_and_the_image_root_must_be_a_root(tmp_path):
    before, after = checkout(tmp_path, "before", SAME), checkout(tmp_path, "after", SAME)
    argv = argv_for(tmp_path, before, after, "image-mode", "mount")
    with pytest.raises(SystemExit):
        rba.main(argv[:-2])                                       # no --expect for "mount"
    with pytest.raises(SystemExit):
        rba.main(argv[:argv.index("--image-mode") + 1] + ["nope"] + argv[argv.index("--image-mode") + 2:])


@pytest.mark.parametrize("bad", ["nolabel", "x=onlyroot", "=a:b"])
def test_a_malformed_root_is_refused(bad):
    with pytest.raises(SystemExit):
        rba.parse_roots([bad])


IMPORTS = "def recompute(run_root, contract_path):\n    import module_that_is_not_installed\n"
KEEPS_PATH = ("def recompute(run_root, contract_path):\n"
              "    import teleop_stand_in\n"
              "    return {'status': 'PASSED', 'run': teleop_stand_in.NAME, 'reasons': []}\n")


def test_an_import_error_on_both_sides_is_a_setup_failure_not_a_pass(tmp_path, capsys):
    before, after = checkout(tmp_path, "before", IMPORTS), checkout(tmp_path, "after", IMPORTS)
    (row,) = compare(tmp_path, before, after, "r")
    assert row["before"] == row["after"] == "IMPORT_FAILED" and not row["usable"]
    assert rba.main(argv_for(tmp_path, before, after, "r")) == 1 and "RESULT: FAIL" in capsys.readouterr().out


def test_the_run_is_refused_when_the_ros_environment_is_missing(tmp_path, capsys):
    before, after = checkout(tmp_path, "before", SAME), checkout(tmp_path, "after", SAME)
    (row,) = compare(tmp_path, before, after, "r", require_modules=("control_msgs_that_is_not_installed",))
    assert row["before"] == row["after"] == "IMPORT_FAILED" and not row["usable"]
    argv = argv_for(tmp_path, before, after, "r")
    argv[argv.index("--require-module") + 1] = "control_msgs_that_is_not_installed"
    assert rba.main(argv) == 1


def test_the_default_requirement_is_control_msgs(tmp_path):
    before, after = checkout(tmp_path, "before", SAME), checkout(tmp_path, "after", SAME)
    (row,) = rba.compare(roots(tmp_path, "r"), before, after, sys.executable, tmp_path / "out", require_modules=("control_msgs",))
    try:
        import control_msgs  # noqa: F401
    except ImportError:
        assert row["before"] == "IMPORT_FAILED"      # no ROS here: the refusal that stops a vacuous pass
    else:
        assert row["usable"] is False or row["before"] == "PASSED"


def test_the_caller_pythonpath_stays_importable_behind_the_shim(tmp_path, monkeypatch):
    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "teleop_stand_in.py").write_text("NAME = 'teleop'\n")
    monkeypatch.setenv("PYTHONPATH", str(extra))
    before, after = checkout(tmp_path, "before", KEEPS_PATH), checkout(tmp_path, "after", KEEPS_PATH)
    (row,) = compare(tmp_path, before, after, "r", expected={"r": "PASSED"})
    assert row["same"] and row["usable"] and row["before"] == "PASSED"
