"""The Head neck limits live in one Python module; the guard consumes them from there.

The controller holds no limits of its own: the broker-era pin tests went with the broker.
"""

import importlib
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[3]


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
