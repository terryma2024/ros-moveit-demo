"""An unexpected exception in the processor's own deterministic logic is a fault (REFUSED, not retried), not a lost processor.

A crash of the `act_offline_episode` child (rc 4, a signal, a timeout) stays an infrastructure failure: `test_processor_processing.py`
covers those. Retrying a deterministic defect three times would only burn the phase-2 budget."""

import pytest

from test_processor_processing import FakeRunner, Fixture, execution


def broken(error):
    def hook(*args, **kwargs):
        raise error
    return hook


@pytest.mark.parametrize("where", ["memo", "grader"])
def test_an_unexpected_exception_in_the_processors_logic_is_a_refusal_with_its_type_and_message(tmp_path, where):
    fixture = Fixture(tmp_path)
    error = RuntimeError("boom 42")
    hooks = dict(memo=broken(error)) if where == "memo" else dict(grader=broken(error))
    result = execution(fixture, FakeRunner(0), **hooks).run()
    assert (result["outcome"], result["retryable"]) == ("REFUSED", False)
    assert "RuntimeError" in result["reason"] and "boom 42" in result["reason"]
    assert result["processed_result"] is None and not (fixture.output_dir / "processed-result.json").exists()


def test_an_unexpected_exception_while_verifying_the_phase_one_record_is_a_refusal(tmp_path, monkeypatch):
    from so101_demo.runtime.act_processor import processing

    fixture = Fixture(tmp_path)
    monkeypatch.setattr(processing, "verify_recording_receipt", broken(AttributeError("odd")))
    result = execution(fixture, FakeRunner(0)).run()
    assert (result["outcome"], result["retryable"]) == ("REFUSED", False) and "AttributeError" in result["reason"]


def test_a_child_crash_is_still_an_infrastructure_failure(tmp_path):
    result = execution(Fixture(tmp_path), FakeRunner(4, write=False)).run()
    assert (result["outcome"], result["retryable"]) == ("INFRASTRUCTURE_FAILURE", True)
