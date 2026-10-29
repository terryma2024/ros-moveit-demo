"""No source module of the four Python-facing packages exceeds the module size limit.

A module past ``MAX_LINES`` is split by responsibility (a package of focused modules, or collaborator mixins for a
large class). A module that cannot be split cleanly goes in ``ALLOWED`` with the reason; an allowed entry whose
file is back under the limit (or gone) is itself a failure, so the allowlist only shrinks.
"""

import style_inventory as inventory
from paths import REPOSITORY

MAX_LINES = 1200
SOURCE_SUFFIXES = (".py", ".cpp", ".hpp", ".c", ".h")
#: repository-relative path -> why it may exceed the limit (empty: every module fits)
ALLOWED: dict[str, str] = {
    "src/so101_demo_py/src/control/moveit/_ik_numeric.c": "Cython output generated from _ik_numeric.pyx; the .pyx is the source and is short",
}
SOURCE_TREES = {
    "so101_demo_py": ("src", "include"),
    "so101_teleop": ("so101_teleop",),
    "so101_quik": ("so101_quik",),
    "so101_mujoco_support": ("src", "include"),
}


def _source_files():
    for package, trees in SOURCE_TREES.items():
        for tree in trees:
            root = REPOSITORY / "src" / package / tree
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if (
                    path.is_file()
                    and path.suffix in SOURCE_SUFFIXES
                    and not set(path.parts) & inventory.EXCLUDED_PARTS
                ):
                    yield path


def _line_counts() -> dict[str, int]:
    return {
        path.relative_to(REPOSITORY).as_posix(): len(path.read_text(encoding="utf-8").splitlines())
        for path in _source_files()
    }


def test_no_source_module_is_over_the_limit():
    too_long = {path: count for path, count in _line_counts().items() if count > MAX_LINES and path not in ALLOWED}

    assert too_long == {}, (
        f"split these modules by responsibility (limit {MAX_LINES} lines): "
        + ", ".join(f"{path} ({count})" for path, count in sorted(too_long.items(), key=lambda item: -item[1]))
    )


def test_every_allowed_module_is_still_over_the_limit():
    counts = _line_counts()
    stale = sorted(path for path in ALLOWED if counts.get(path, 0) <= MAX_LINES)

    assert stale == [], "delete these entries from ALLOWED, the modules fit now: " + ", ".join(stale)


def test_every_allowed_module_has_a_reason():
    assert all(reason.strip() for reason in ALLOWED.values())


def test_the_scan_sees_the_split_modules():
    counts = _line_counts()

    assert "src/so101_demo_py/src/runtime/parallel_perception_runtime.py" in counts
    assert "src/so101_mujoco_support/src/simulation_evidence_plugin.cpp" in counts
