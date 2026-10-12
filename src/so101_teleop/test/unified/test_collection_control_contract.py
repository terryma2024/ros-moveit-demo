"""Collection control starts one private Worker run, not a pick-place phase."""

import json
import pytest

from so101_teleop.unified.ipc import decode_request,IpcProtocolError


def packet():
    return dict(version=1,operation='act_collection_start',command_id='run',deadline_ns=1000,
        service_epoch='epoch',runtime_id='runtime',service_token='token',campaign_id='campaign',worker_id='w00',
        session_id='session',attempt_id='wave-0',execution_generation=1,
        token=dict(operation_id='op',child_id='w00',runtime_id='runtime',execution_generation=1,
                   deadline_ns=1000,revocation_revision=0),
        payload=dict(worker_spec=dict(path='/evidence/wave-0/w00/g1/control/worker-spec.json',sha256='a'*64),
            launch_generation=1,manifest_sha256='b'*64,runtime_config_sha256='c'*64,
            collection_config_sha256='d'*64,contact_policy_fingerprint='e'*64))


def test_collection_start_accepts_only_frozen_worker_run_reference():
    value=packet()
    parsed=decode_request(json.dumps(value).encode(),now_ns=1)
    assert parsed.payload==value['payload']


@pytest.mark.parametrize('problem',['extra','missing','bool_generation','legacy_phase'])
def test_collection_start_refuses_unknown_or_legacy_phase_payload(problem):
    value=packet()
    if problem=='extra':value['payload']['execute_command']='arbitrary'
    elif problem=='missing':value['payload'].pop('worker_spec')
    elif problem=='bool_generation':value['payload']['launch_generation']=True
    else:value['payload']={'scenario_id':'case-1','support_distance_max_m':.001}
    with pytest.raises(IpcProtocolError):decode_request(json.dumps(value).encode(),now_ns=1)
