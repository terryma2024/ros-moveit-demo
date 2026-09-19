"""A revoke creates a stop barrier before any new owner can acquire control."""
import pytest
from so101_demo.act.ownership import Ownership


def test_teacher_cannot_acquire_or_reuse_act_lease():
    owner=Ownership(); token=owner.acquire('act','s','a')
    with pytest.raises(PermissionError):owner.acquire('teacher','s','a')
    with pytest.raises(PermissionError):owner.require(token,'teacher','s','a')
    owner.revoke('STOP')
    with pytest.raises(PermissionError):owner.require(token,'act','s','a')
    with pytest.raises(PermissionError):owner.acquire('teacher','s','a')
    assert owner.state=='STOPPING'
    owner.confirm_stopped(True); new=owner.acquire('teacher','s','b')
    assert new!=token


def test_release_needs_stop_and_scope_and_old_ticket_is_fenced():
    owner=Ownership();token=owner.acquire('teacher','s','a')
    ticket=owner.ticket(token,'teacher','s','a')
    with pytest.raises(PermissionError):owner.release(token,False)
    with pytest.raises(PermissionError):owner.require(token,'teacher','s','other')
    owner.release(token,True);owner.acquire('teleop','s','b')
    with pytest.raises(PermissionError):owner.require_ticket(ticket)
    with pytest.raises(PermissionError):owner.release(token,True)


def test_expiry_revokes_and_blocks_until_real_stop():
    now=[10.];owner=Ownership(monotonic=lambda:now[0],lease_timeout_s=1.)
    token=owner.acquire('recovery','s','a');now[0]=11.
    with pytest.raises(PermissionError):owner.require(token,'recovery','s','a')
    assert owner.state=='STOPPING'
    with pytest.raises(PermissionError):owner.acquire('teacher','s','a')
    with pytest.raises(PermissionError):owner.confirm_stopped(False)
    owner.confirm_stopped(True);assert owner.state=='IDLE'


@pytest.mark.parametrize('owner',['unknown','',True])
def test_closed_owner_set(owner):
    with pytest.raises((ValueError,TypeError)):Ownership().acquire(owner,'s','a')
