"""Approval is trusted, attempt/epoch scoped, expiring and consumed exactly once."""
import copy
import pytest
from so101_demo.act.permits import PermitAuthority
from test_act_execution import prefix


def authority():
    now=[10.];generation=[2]
    snapshot={'session_id':'s','attempt_id':'a','reset_epoch':3,'sim_time_s':1.,'positions':(0.,)*6}
    calls=[]
    port=PermitAuthority(snapshot_port=lambda:copy.deepcopy(snapshot),
        check_port=lambda p,s:calls.append((p,s)) or True,
        generation_port=lambda:generation[0],monotonic=lambda:now[0],ttl_s=.04)
    return port,now,generation,snapshot,calls


def test_approval_binds_content_snapshot_and_is_one_use():
    port,now,generation,snapshot,calls=authority();p=prefix();permit=port.approve(p)
    assert len(calls)==1 and len(permit['snapshot_sha256'])==64
    port.require(permit,p)
    with pytest.raises(PermissionError):port.require(permit,p)
    permit=port.approve(p);changed=dict(p,positions=((.03,)*6,(.04,)*6))
    with pytest.raises(PermissionError):port.require(permit,changed)
    with pytest.raises(PermissionError):port.require(permit,p)


@pytest.mark.parametrize('change',('expiry','epoch','generation','attempt','tamper','revoke'))
def test_invalid_approval_never_reaches_driver(change):
    port,now,generation,snapshot,_=authority();p=prefix();permit=port.approve(p)
    if change=='expiry':now[0]=permit['valid_until_wall_s']
    elif change=='epoch':snapshot['reset_epoch']+=1
    elif change=='generation':generation[0]+=1
    elif change=='attempt':snapshot['attempt_id']='other'
    elif change=='tamper':permit['snapshot_sha256']='0'*64
    else:port.revoke('hazard')
    with pytest.raises(PermissionError):port.require(permit,p)


def test_unapproved_path_does_not_issue_a_permit():
    port,*_=authority();port.check_port=lambda p,s:False
    with pytest.raises(PermissionError,match='PATH_REJECTED'):port.approve(prefix())


def test_contact_revocation_preempts_slow_path_check_and_fences_late_approval():
    import threading
    port,*_=authority();entered=threading.Event();release=threading.Event();revoked=threading.Event();results=[]
    def delayed(p,s):entered.set();release.wait(1.);return True
    port.check_port=delayed
    def approve():
        try:results.append(port.approve(prefix()))
        except PermissionError as error:results.append(str(error))
    worker=threading.Thread(target=approve);worker.start();assert entered.wait(.2)
    stop=threading.Thread(target=lambda:(port.revoke('robot_contact'),revoked.set()));stop.start()
    try:assert revoked.wait(.05),'Stop was serialized behind physics computation'
    finally:release.set();worker.join(.2);stop.join(.2)
    assert results==['PERMIT_GENERATION_INVALID']


def test_changed_current_physical_path_is_rechecked_before_consumption():
    port,*_=authority();p=prefix();permit=port.approve(p)
    port.check_port=lambda p,s:False
    with pytest.raises(PermissionError):port.require(permit,p)
    with pytest.raises(PermissionError):port.require(permit,p)
