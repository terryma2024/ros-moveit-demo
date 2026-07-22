# PickPlaceTargetPolicy Design

## Goal

Remove duplicated TCP target poses from planners and transition validators. A shared target
policy becomes the only component that selects the TCP target for a workflow transition.

## Interfaces

`PickPlaceTargetPolicy` is an abstract policy with two operations:

- `targetPose(current_state, next_state, observation)` returns either a `Pose3d` or a structured
  `Failure`.
- `configurationSignature()` identifies every input that can change target selection and is
  included in the checkpoint configuration hash.

`FixedPickPlaceTargetPolicy` is the current implementation. It maps
`MOVE_ABOVE_OBJECT -> DESCEND` to `(0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0)` and
`DESCEND -> CLOSE_GRIPPER` to `(0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0)`. Unsupported transitions
fail closed. It accepts but does not inspect the observation; a future model-backed policy may
use the complete observation without changing consumers.

## Data Flow

The Runner observes once before planning. It passes that exact `ObservationResult`, together
with the current and successful-next states, to the registered planner. The Planner asks the
injected policy for its pose. The transition Validator receives the same policy and resolves the
expected pose from the transition's pre-execution snapshot, so both consumers use the same state
pair and observation data.

Plan-only also obtains one observation, using the MoveIt planner's observer adapter when Gazebo
observation is not required. Observation here supplies policy input; plan-only still performs no
post-execution validation.

## Error Handling and Resume

Missing observations, policy failures, and unsupported transitions produce explicit failures;
no default pose is substituted. The fixed policy signature is added to the configuration hash,
so changing fixed targets or a future policy model invalidates incompatible checkpoints.

## Testing

Unit tests cover both fixed mappings, unsupported transitions, Planner receipt of the Runner's
pre-execution observation, Validator use of the injected policy, and policy signature effects on
configuration identity. Existing workflow, resume, formatter, and lint tests remain green.
