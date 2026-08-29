# SO-101 unified Python demo

`so101_demo_py` is the sole ROS package and runtime-resource owner for the SO-101
MuJoCo and Gazebo pick-place demos. Its import namespace is `so101_demo`, stored directly
under this package's `src/` directory.

## Launchers

After sourcing the selected install overlay, choose the simulator explicitly:

```bash
ros2 launch so101_demo_py so101_mujoco.launch.py
ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py
ros2 launch so101_demo_py so101_gazebo.launch.py
ros2 launch so101_demo_py so101_gazebo_pick_place.launch.py
```

All launchers default to `run_mode:=dry_run execute:=false`. Live simulation requires the
explicit pair `run_mode:=execute execute:=true`. Select the qualified policy with
`policy_id:=light_cup_wall_pick policy_version:=v1`; the launcher fixes the backend and
never falls back to another simulator.

The Gazebo path runs the common application and reports the phase at which the policy or
controller succeeds or fails. Gazebo is not a qualification backend because it does not
provide the lossless physics-step evidence required by the MuJoCo gate.

## Shared operator commands

Planning Scene, camera, and reset use one public command per operation. Select the
simulator explicitly; omitting `--backend` retains the MuJoCo-compatible behavior.

```bash
ros2 run so101_demo_py scene_setup --backend gazebo setup
ros2 run so101_demo_py scene_setup --backend gazebo observe
ros2 run so101_demo_py camera_preset --backend gazebo overview
ros2 run so101_demo_py teleop_reset --backend gazebo --session-id operator-reset-001
```

The common geometry manifest is the only table/pedestal/plastic-cup contract. Both
Planning Scene backends apply it and require independent read-back with primitive counts
`1/1/13`. Gazebo camera commands require a positive `/gui/move_to/pose` acknowledgement.
Gazebo reset is a complete first-failure transaction: it cancels goals, verifies physical
and MoveIt detach, parks and restores the cup, synchronizes the scene, opens the gripper,
plans and executes the exact `home` plan, and verifies Gazebo, MoveIt, controllers, joints,
velocities, and TF before returning success.

## Text pick agent (V5-T003)

`text_pick_agent` turns one bounded instruction into one *candidate* task; fixed code, not
the model, decides whether it can reach the existing `dynamic_cup_pick_place` runtime.
The complete learner workflow, process map, ROS interfaces, safe provider setup, confirmation
flow, and evidence boundaries are in [the Text Pick Agent guide](docs/text_pick_agent.md).
Preview is the default and has no runtime dispatch:

```bash
ros2 run so101_demo_py text_pick_agent \
  --instruction "帮我拿杯子" \
  --request-id preview-001 \
  --backend mujoco
```

The cloud primary reads its key only from `DEEPSEEK_API_KEY`; do not put a key on the command
line or in files. If the DeepSeek provider fails, the chain tries the local Ollama fallback once,
at `http://127.0.0.1:11434/api/chat` with the default model `qwen3.5:4b`. A syntactically valid
provider result is still untrusted. It must first select one closed outcome branch:

```json
{
  "outcome": "supported",
  "command": {
    "target_object": "plastic_cup",
    "action": "pick",
    "constraints": {}
  }
}
```

`unsupported` and `ambiguous` carry only the outcome field and terminate before Dispatcher;
only `supported` carries the exact current TaskCommand. There are no extra fields. V5-T003 has
no downstream constraint consumer, so every nonempty `constraints` object is rejected.

Execution requires both authorization flags, the exact digest from an inspected preview, the
qualified MuJoCo backend, and verified current runtime provenance. Resolve the source commit and
installed prefix immediately before running—do not copy an old SHA:

```bash
ros2 run so101_demo_py text_pick_agent \
  --instruction "帮我拿杯子" \
  --request-id v5-t003-live-001 \
  --backend mujoco \
  --mode execute \
  --execute \
  --confirmation-digest "$CONFIRMATION_DIGEST_FROM_PREVIEW" \
  --session-id v5-t003-live-001 \
  --expected-reset-epoch 0 \
  --evidence-root /tmp/so101-debug-v5-t003-text-agent-20260829-164105 \
  --source-commit "$(git rev-parse HEAD)" \
  --installed-prefix "$(ros2 pkg prefix so101_demo_py)"
```

The fixed gate order is input check, Planner outcome, closed TaskCommand validation, capability
whitelist, double authorization, `backend=mujoco`, digest equality, atomic request claim, then the
runtime. A `DISPATCH_PREVIEW` proves only static validation with `dispatch=false`.
`RUNTIME_STARTED` in `state_trace` proves only that executor dispatch was attempted;
`RUNTIME_COMPLETED` is only the runtime return status. Neither is V5-T005 physical proof.

## Evidence and lifecycle

Pass `evidence_file:=/absolute/path/result.json` for an execute launch. The common manifest
links backend evidence under the sibling `result.d` directory and records source, policy,
bundle, session, reset epoch, and the first failed phase when applicable.

MuJoCo qualification keeps two lifecycle batches separate:

- `FULL_RESTART`: every counted run owns an independent simulator/ROS stack.
- `RESET_WORLD`: one owned stack is reset to a newly observed epoch between counted runs.

Results from one lifecycle never count toward the other lifecycle's denominator.

## Real-arm boundary

`real_stub` parses only the committed fail-closed safety mapping. It has no launcher and
performs no device discovery, serial/socket access, ROS control I/O, planning, execution,
gripper command, reset, stop, or recovery. Every operation returns
`REJECTED / REAL_HARDWARE_NOT_CONFIGURED`. Real hardware enablement requires a separate
safety design and implementation.

## Static acceptance gate

From a shell sourced with the isolated project overlay, run:

```bash
SO101_DEMO_EXPECTED_PREFIX="$(ros2 pkg prefix so101_demo_py)" \
  src/so101_demo_py/scripts/check_fusion_contract.sh
```

The gate verifies package discovery, the installed prefix, executables, launchers, assets,
frozen policy bytes, backend boundaries, repository ownership, zero-I/O real-stub symbols,
and a clean textual diff.
