"""A proven path must never enter the legacy absolute-goal branch."""

import pytest

from so101_demo.act.execution import ActExecutionAdapter

from test_act_execution import Port
from test_act_path_proof_permits import proof_authority
from test_act_physics import scene


def test_proof_without_commit_ports_cannot_send_fake_goals(scene):
    authority, prefix, _, checks = proof_authority(scene)
    permit = authority.approve(prefix)
    arm, gripper = Port(), Port()
    adapter = ActExecutionAdapter(
        arm, gripper, permit_port=authority,
        sim_clock=lambda: 1., monotonic=lambda: 10.,
        progress=lambda: None, submit_lead_s=.03,
        accept_timeout_s=.02, stop_timeout_s=.03,
        reference_port=lambda _: prefix['positions'][0],
    )
    adapter.begin_attempt('s', 'a')
    with pytest.raises(PermissionError, match='PROOF_COMMIT_PORT_REQUIRED'):
        adapter.submit(prefix, permit)
    assert arm.goals == gripper.goals == []
    assert checks == [1]
