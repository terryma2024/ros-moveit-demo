"""Task 11: only a committed, clean, complete success may enter training."""

import pytest

from so101_demo.act.collection import training_eligible


def _record(**overrides):
    record = {"status": "PASSED", "qc": "PASS", "done": True, "interventions": 0,
              "coordinator_committed": True}
    record.update(overrides)
    return record


def test_failure_is_retained_but_not_exported():
    assert not training_eligible({"qc": "PASS", "done": False, "interventions": 0})
    assert not training_eligible({"qc": "FAIL", "done": True, "interventions": 0})
    assert not training_eligible({"qc": "PASS", "done": True, "interventions": 0,
                                  "status": "PASSED", "coordinator_committed": False})


def test_only_a_committed_clean_success_is_eligible():
    assert training_eligible(_record())
    for key, value in (("status", "FAILED"), ("qc", "FAIL"), ("done", False),
                       ("interventions", 1), ("coordinator_committed", False)):
        assert not training_eligible(_record(**{key: value})), key
    # an incomplete record is refused, not raised out of: the plan's Step-1 case has exactly this
    # shape and expects False
    assert not training_eligible({"qc": "PASS", "done": True, "interventions": 0})
