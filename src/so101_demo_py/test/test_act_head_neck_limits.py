"""The Head neck limits live in one Python module; the guard consumes them from there.

Until the broker-owned controller is deleted, the module is also pinned to the broker's
head-mode constants (same repository, read as source text).
"""

import importlib
import re
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[3]
BROKER = REPOSITORY / 'src/so101_mujoco_support/src/broker_owned_trajectory_controller.cpp'


def limits():
    return importlib.import_module('so101_demo.act.head_neck_limits')


def test_limits_match_the_design_values():
    module = limits()
    assert module.MAX_VELOCITY_RAD_S == 1.0
    assert module.MAX_ACCELERATION_RAD_S2 == 2.0
    assert module.QUIET_VELOCITY_RAD_S == 0.04136050464213824
    assert module.MEASURED_POSITION_MISMATCH_RAD == 0.002
    assert module.MIN_DURATION_NS == 100_000_000
    assert module.MAX_DURATION_NS == 5_000_000_000
    assert module.HEADER_LEAD_NS == 4_000_000
    assert module.CONSUMING_TICK_ALLOWANCE_NS == 14_000_000
    assert module.STOP_WINDOW_SAMPLES == 51
    assert module.STOP_WINDOW_STEP_NS == 2_000_000
    assert module.STOP_WINDOW_MAX_VELOCITY_RAD_S == 0.002
    assert module.STOP_WINDOW_MAX_AGE_NS == 200_000_000
    assert module.STOP_WINDOW_QOS_DEPTH == 64
    assert module.STOP_WINDOW_DEADLINE_S == 0.5


def test_limits_equal_the_broker_head_mode_constants():
    source = BROKER.read_text()

    def constant(name):
        match = re.search(r'constexpr double %s = ([0-9.eE+-]+);' % name, source)
        assert match, name
        return float(match.group(1))

    module = limits()
    assert module.MAX_VELOCITY_RAD_S == constant('kHeadVelocityLimit')
    assert module.MAX_ACCELERATION_RAD_S2 == constant('kHeadAccelerationLimit')
    assert module.QUIET_VELOCITY_RAD_S == constant('kHeadMeasuredVelocityLimit')
    assert module.MEASURED_POSITION_MISMATCH_RAD == constant('kHeadMeasuredPositionMismatchLimit')
    assert module.GEOMETRY_ABS_LIMIT_RAD == constant('kHeadGeometryLimit')
    assert '14000000LL' in source and module.CONSUMING_TICK_ALLOWANCE_NS == 14_000_000
    assert '100000000LL' in source and '5000000000LL' in source


def test_stop_window_constants_equal_the_native_witness():
    header = (REPOSITORY / 'src/so101_mujoco_support/include/so101_mujoco_support/'
              'controller_stop_witness.hpp').read_text()
    module = limits()
    assert int(re.search(r'required_samples = (\d+);', header).group(1)) == module.STOP_WINDOW_SAMPLES
    assert int(re.search(r'step_ns = (\d+);', header).group(1)) == module.STOP_WINDOW_STEP_NS
    assert int(re.search(r'max_age_ns = (\d+);', header).group(1)) == module.STOP_WINDOW_MAX_AGE_NS
    assert float(re.search(r'stop_velocity_rad_s = ([0-9.]+);', header).group(1)) == \
        module.STOP_WINDOW_MAX_VELOCITY_RAD_S


def test_the_guard_takes_its_limits_from_the_module():
    from so101_demo.adapters.act import head_trajectory_guard as guard
    module = limits()
    assert guard._QUIET_VELOCITY == module.QUIET_VELOCITY_RAD_S
    assert guard._MAX_VELOCITY == module.MAX_VELOCITY_RAD_S
    assert guard._MAX_ACCELERATION == module.MAX_ACCELERATION_RAD_S2
    assert guard._MIN_DURATION_NS == module.MIN_DURATION_NS
    assert guard._MAX_DURATION_NS == module.MAX_DURATION_NS
    assert guard._LEAD_NS == module.HEADER_LEAD_NS
    assert guard._MIN_FIRST_OFFSET_NS == module.MIN_FIRST_OFFSET_NS
    assert guard._MAX_FIRST_OFFSET_NS == module.MAX_FIRST_OFFSET_NS
    source = Path(guard.__file__).read_text()
    assert 'head_neck_limits' in source
    for literal in ('0.04136050464213824', '5_000_000_000', '100_000_000'):
        assert literal not in source, literal
