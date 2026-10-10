"""Head neck limits and stop-window constants: the one Python home.

The guard (``adapters/act/head_trajectory_guard.py``) and the stop-window evaluator both read
these values. The controller holds no limits of its own. While the broker-owned controller
still exists, ``test_act_head_neck_limits.py`` pins every value here to the broker's
head-mode constants; after that controller is deleted the pin test goes with it.
"""

# ---- trajectory shape (exact at the guard, before dispatch) ----------------------------
MAX_VELOCITY_RAD_S = 1.0
MAX_ACCELERATION_RAD_S2 = 2.0
#: the broker's ``kHeadGeometryLimit``: the absolute position the neck may ever be commanded to
GEOMETRY_ABS_LIMIT_RAD = 6.283175307179587
MIN_DURATION_NS = 100_000_000
MAX_DURATION_NS = 5_000_000_000
#: fixed header lead of every sealed goal
HEADER_LEAD_NS = 4_000_000
MIN_FIRST_OFFSET_NS = 50_000_000
MAX_FIRST_OFFSET_NS = 600_000_000

# ---- measured-prefix envelope (approximated at the guard) ------------------------------
QUIET_VELOCITY_RAD_S = 0.04136050464213824
MEASURED_POSITION_MISMATCH_RAD = 0.002
#: native first-update timing allowance (the consuming control tick)
CONSUMING_TICK_ALLOWANCE_NS = 14_000_000
CONSUMING_TICK_ALLOWANCE_S = 0.014
#: envelope growth factor of the measured-prefix check
PREFIX_ENVELOPE_VELOCITY_FACTOR = 0.4

# ---- collision path sampling ------------------------------------------------------------
PATH_STEP_S = 0.002
CLEARANCE_M = 0.001
MAX_SAMPLES = 50_000
PATH_MAX_SPACING_MOTION_RAD = 0.001
PREFIX_MAX_SPACING_MOTION_RAD = PATH_MAX_SPACING_MOTION_RAD

# ---- stop window (design section 3) ------------------------------------------------------
#: consecutive ``controller_state`` samples on the 2 ms sim-stamp grid
STOP_WINDOW_SAMPLES = 51
STOP_WINDOW_STEP_NS = 2_000_000
STOP_WINDOW_MAX_VELOCITY_RAD_S = 0.002
#: monotonic receive age bound, measured at the moment the window completes
STOP_WINDOW_MAX_AGE_NS = 200_000_000
#: reliable subscription depth of the window subscriber
STOP_WINDOW_QOS_DEPTH = 64
#: ``head_stop_window_deadline_s`` (provisional until it becomes a policy field in startup protocol v2)
STOP_WINDOW_DEADLINE_S = 0.5
#: startup shadow bound: shadow complete <= native PREARM READY sim stamp + this
STOP_WINDOW_STARTUP_SLACK_NS = 102_000_000
