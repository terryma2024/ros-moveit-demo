"""The offline lock recount applies the same strict start and hold band as the controller (audit deadband 3 px)."""
import pytest

from head_run_audit_support import make_reader
from test_act_head_run_audit import audit, observation_records, verdict


def locks(tmp_path, monkeypatch, offsets, counts):
    records = []
    for number, (offset, count) in enumerate(zip(offsets, counts), start=1):
        records += observation_records(sequence=number, lock=count, center=320+offset, frame=number*100000000)
    return verdict(audit(make_reader(tmp_path, records, monkeypatch)), 'HFA-008')


def test_a_hold_band_frame_inside_a_running_lock_recounts(tmp_path, monkeypatch):
    assert locks(tmp_path, monkeypatch, (2., 5.5, 2.), (1, 2, 3)) == 'HOLDS'


def test_a_hold_band_frame_cannot_start_a_lock_run(tmp_path, monkeypatch):
    assert locks(tmp_path, monkeypatch, (5.5, 2., 2.), (1, 2, 3)) == 'VIOLATED'


def test_a_frame_beyond_the_hold_band_cannot_extend_a_lock_run(tmp_path, monkeypatch):
    assert locks(tmp_path, monkeypatch, (2., 6.5, 2.), (1, 2, 3)) == 'VIOLATED'


@pytest.mark.parametrize('offset, verdict_name', [(6., 'HOLDS'), (6.01, 'VIOLATED')])
def test_hold_band_edge_is_inclusive(tmp_path, monkeypatch, offset, verdict_name):
    assert locks(tmp_path, monkeypatch, (3., offset, 3.), (1, 2, 3)) == verdict_name
