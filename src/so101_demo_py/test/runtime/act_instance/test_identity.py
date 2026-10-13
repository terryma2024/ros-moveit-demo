"""The fixed ROS identity of an ACT instance and the explicit instance marker that replaces the namespace marker."""

import pytest

from so101_demo.runtime.act_instance import identity
from so101_demo.ros import process_init


def test_the_identity_is_domain_181_in_the_root_namespace():
    assert identity.ACT_INSTANCE_ROS_DOMAIN_ID == 181
    assert identity.ACT_INSTANCE_ROS_NAMESPACE == '/'


def test_the_environment_has_the_fixed_domain_localhost_discovery_and_no_namespace():
    entries = identity.instance_environment(mujoco_session_id='act-abc-w00-g1')

    assert entries == ['ROS_DOMAIN_ID=181', 'MUJOCO_GL=egl', 'ROS_LOCALHOST_ONLY=1',
                       'ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST', 'SO101_MUJOCO_SESSION_ID=act-abc-w00-g1']
    assert not any(entry.startswith('ROS_NAMESPACE') for entry in entries)
    for session in ('', None, 7):
        with pytest.raises(ValueError, match='^ACT_INSTANCE_SESSION_INVALID$'):
            identity.instance_environment(mujoco_session_id=session)


def environ(**overrides):
    values = dict(entry.split('=', 1) for entry in identity.instance_environment(mujoco_session_id='s1'))
    values.update(overrides)
    return {name: value for name, value in values.items() if value is not None}


def test_a_fixed_environment_verifies_and_every_drift_is_refused():
    identity.verify_instance_environment(environ(), session_id='s1')
    identity.verify_instance_environment(environ(ROS_NAMESPACE=''))
    for drifted in (environ(ROS_DOMAIN_ID='182'), environ(ROS_DOMAIN_ID=None), environ(MUJOCO_GL='osmesa'),
                    environ(ROS_NAMESPACE='/act/w00'), environ(ROS_LOCALHOST_ONLY='0'),
                    environ(ROS_AUTOMATIC_DISCOVERY_RANGE='SUBNET'), environ(SO101_MUJOCO_SESSION_ID='other')):
        with pytest.raises(ValueError, match='^ACT_INSTANCE_ENVIRONMENT_DRIFT$'):
            identity.verify_instance_environment(drifted, session_id='s1')
    with pytest.raises(ValueError, match='^ACT_INSTANCE_ENVIRONMENT_DRIFT$'):
        identity.verify_instance_environment(None)


def test_the_marker_is_absent_by_default_and_names_the_owned_root_once_set(tmp_path):
    values = {}
    assert identity.instance_root(environment=values) is None
    identity.mark_instance(tmp_path, environment=values)
    assert values == {identity.INSTANCE_ROOT_ENV: str(tmp_path)}
    assert identity.instance_root(environment=values) == str(tmp_path)
    for bad in ('relative/root', str(tmp_path) + '/../x', ''):
        with pytest.raises(ValueError, match='^ACT_INSTANCE_ROOT_INVALID$'):
            identity.instance_root(environment={identity.INSTANCE_ROOT_ENV: bad})
    with pytest.raises(ValueError, match='^ACT_INSTANCE_ROOT_INVALID$'):
        identity.mark_instance('relative', environment={})


def test_the_marker_is_not_the_namespace_marker(tmp_path):
    values = {identity.INSTANCE_ROOT_ENV: str(tmp_path)}

    assert 'NAMESPACE' not in identity.INSTANCE_ROOT_ENV
    assert process_init.in_instance_process(environment=values) is True
    assert process_init.in_instance_process(environment={}) is False


def test_an_instance_process_owns_its_signals_and_adds_no_namespace_arguments(tmp_path):
    from rclpy.signals import SignalHandlerOptions

    options = process_init.global_init_options(environment={identity.INSTANCE_ROOT_ENV: str(tmp_path)})

    assert options == dict(signal_handler_options=SignalHandlerOptions.NO)
    assert 'args' not in options


def test_a_generic_process_keeps_the_bare_init():
    assert process_init.global_init_options(environment={}) == {}
    assert process_init.global_init_options(environment={'ROS_DOMAIN_ID': '181'}) == {}
