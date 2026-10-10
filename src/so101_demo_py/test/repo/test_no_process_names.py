"""No new process name enters the code base, and the allowlist of existing ones only shrinks.

A process name is a whole segment that names a work step instead of a business concept: ``task<n>``, ``t8``,
``w<d>``, ``n1``, ``hs<n>``, ``cp<n>``, ``exp<n>``, ``p<d>``, ``b<n>[b]``, ``d<d>``, ``rec<n>[b]`` or
``r<n>[b]``. The scan covers file and directory names, console script names and module-level ``def`` /
``class`` / constant names. Geometry identifiers such as ``x1``, ``q6`` and ``dq1`` occur inside functions, so
they are not scanned. The process-name allowlist must be empty, except for reasoned ``permanent`` entries, at
the end of phase C.
"""

import pytest
import style_inventory as inventory
from paths import TEST_ROOT

ALLOWLIST = TEST_ROOT / "repo" / "style_allowlist.tsv"


@pytest.mark.parametrize(
    "name",
    ["task8_live", "Task8Runner", "macos_w2_campaign", "EXACT_W1_WORKERS", "macos_n1_retry", "hs278_parameters",
     "test_b1b_reset", "test_p3_rework", "LOCAL_R11_COMMIT", "rec12b_capturing", "test_d4_receipt", "cp765_loader",
     "exp115_values", "t8"],
)
def test_a_process_segment_is_detected(name):
    assert inventory.process_segments(name) != []


@pytest.mark.parametrize(
    "name",
    ["x1", "q6", "dq1", "dp", "p", "w", "worker", "network", "bd", "task", "rexp", "SO101_HEAD", "n10", "d", "taskonomy", "w12"],
)
def test_geometry_and_ordinary_words_are_not_process_names(name):
    assert inventory.process_segments(name) == []


def test_the_allowlist_is_well_formed():
    _entries, problems = inventory.load_allowlist(ALLOWLIST)

    assert problems == []


def test_every_process_name_is_in_the_allowlist():
    missing, _unused, _problems = inventory.compare_with_allowlist(inventory.SCAN_PROCESS, ALLOWLIST)

    assert missing == [], (
        "new process names (name them by the business concept, not the step that produced them): "
        + ", ".join(f"{hit.path}::{hit.name}" for hit in missing[:25])
    )


def test_the_allowlist_has_no_process_entry_without_a_hit():
    _missing, unused, _problems = inventory.compare_with_allowlist(inventory.SCAN_PROCESS, ALLOWLIST)

    assert unused == [], "delete these entries from style_allowlist.tsv, their names are gone: " + ", ".join(unused[:25])
