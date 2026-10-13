# SO-101 ACT fixed in-container identity: design amendment and implementation plan

Date: 2026-10-13. Amends `2026-09-30-so101-act-containerized-campaign-design.md` (section 2, the sentence giving each shard its own
ROS Domain and namespace) and builds on `2026-10-12-so101-container-one-way-control-design.md`.

## Human ruling

Design change stated by the user on 2026-10-13:

1. Inside a container the ROS domain id and all names are fixed; isolation comes only from the container.
2. A container run and a non-container single-worker run use the same Teacher demonstration collection logic code; a non-container
   single worker behaves as if it were inside a container.
3. Non-container runs no longer support multiple workers.

Answers to the open questions of section 2 below (2026-10-13):

- Q1 scope of item 3: the non-ACT native multi-worker batch is removed as well. That removal affects Web Expert Validation, the
  native parallel batch tools and the macOS two-worker campaign; it is a separate phase with its own plan and confirmation after the
  ACT change is verified. Tasks 1 to 8 below cover the ACT change only.
- Q2: the non-container single worker uses the same Host campaign flow with a native launcher; the Teacher service stays in its
  container; admission enforces one native instance per host.
- Q3: `act_diagnostic_episode run` is removed after the native instance run is verified; its diagnostic-only features are not ported.
- Q4: the registered unified store is migrated in place after a hashed backup, keeping the old slot rows.
- Q5: the raw bags of the runs on the old topology are re-readable only at commit 64aca49d5.
- Q6: fixed domain 181, a unique simulation session id per instance, the runtime YAML byte-identical.
- Execution of the plan confirmed.

The text below is the investigation and plan as drafted before those answers; where it recommends, the answers above decide.


Read-only investigation; nothing was modified. PROVEN = read in code or evidence at the cited line; INFERRED = reasoned, not executed.

Path prefixes (all absolute):
- `W` = `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a`
- `D` = `W/src/so101_demo_py/src` (imported as `so101_demo`)
- `U` = `W/src/so101_teleop/so101_teleop/unified`
- `X` = `W/src/so101_demo_py/test`
- `REG` = `/data/work/so101-evidence/act-data/20260924-fbc25063-resume`

## 0. Things to know before any edit

1. **EXP-582 was running during this investigation.** At 13:25 CST `docker ps` showed both shards and the Teacher up 21–22 minutes, with the Host CLI as pid 3560061. A later `docker exec` on w00 returned "is not running", so its current state is unknown; I did not interfere. The Host CLI's `--source` and `--collection-config` point at worktree files (`W/src/so101_demo_py/src/backends/mujoco/reset.py`, `W/src/so101_demo_py/config/act/parallel_collection.yaml`), and I infer it imports worktree source via `so101_worktree_import`. No worktree edit should start until that run has settled and is recorded.
2. **Most in-instance code already has the native branch.** Almost every consumer is written as "if `container_ros_namespace()` is None, do the native thing". The change is therefore mostly: stop setting the marker, launch the existing un-namespaced stack, then delete the dead branches.
3. **Three container fixes are keyed on the namespace marker but are not about namespacing.** They must be re-keyed before the marker goes: the private rclpy context in `_RosScope`, `SignalHandlerOptions.NO`, and the bag-root decision.
4. **The frozen runtime YAML cannot drop `ros_domain_ids`.** `D/parallel_batch/contracts/linux_cuda.py:247-254,265-269` enforces `ros_domain_ids == (181..188)` and `max_worker_count == 8` exactly, and the contract is shared with the native batch that Expert Validation uses. The fixed domain has to be a code constant, with the YAML left byte-identical.

## A. Where per-worker domain, namespace and scoped names live

### Launch, spec and Host ownership

| Location | What it carries | Class |
|---|---|---|
| `D/runtime/act_fixed_collection_composition.py:82,98-102` | Slots built from `runtime.ros_domain_ids[:n]`, namespace `/act/campaign_<id>/wNN`, controller `<ns>/arm_controller` | Remove domain, namespace and controller; keep `wNN` |
| `D/runtime/container_campaign/shard_launcher.py:62-85` | Spec `ros_namespace`/`ros_domain_id`; `ContainerLaunch` and `ShardLaunchArgs` copies | Remove; keep session, runtime_id, token, owned root, container name |
| `D/runtime/container_campaign/launch.py:54-70,117-120` | `ShardLaunchArgs.ros_domain_id/ros_namespace`; env `ROS_DOMAIN_ID`, `ROS_NAMESPACE` | Fixed domain from a constant; drop `ROS_NAMESPACE` |
| `launch.py:132-134` | `--network none --ipc private`, localhost-only env | Keep; now the sole isolation |
| `D/cli/campaign_shard.py:24-26,61,84-86` | Spec fields; namespace validation; domain must be in `runtime.ros_domain_ids` | Remove fields, bump spec `schema_version` |
| `campaign_shard.py:168` | `runtime-ready.json` records `ros_namespace` | Remove field |
| `campaign_shard.py:218-223` | Env drift check; sets `SO101_ACT_CONTAINER_NAMESPACE` and `SO101_ACT_CONTAINER_OWNED_ROOT` | Drift check against fixed values; replace namespace marker with an instance marker |
| `campaign_shard.py:235-242` | `ContainerActStackLaunch(ros_namespace=…)`, `NativeShardRetirement(ros_namespace=…)` | Use plain `ActStackLaunch`; drop argument |
| `D/runtime/container_campaign/registry.py:35-36,52-58,145-150,194-195` | Launch record fields; "immutable slot drift" and "live resource overlap" on domain/namespace; stop-evidence read | Remove fields and both collision rules; keep session-reuse and slot-not-retired rules |
| `D/runtime/container_campaign/shard_owner.py:52,66,167-168,177` | Entry/launch equality, spec expectations, bridge args, ready document | Remove |
| `D/runtime/container_campaign/owner.py:150-151` | Shard-versus-slot check on domain/namespace | Simplify to `worker_id` |
| `U/bridge.py:584-602,679-680` | `ContainerBridgeProcessOwner(ros_namespace, ros_domain_id)` | Remove both |

### Stack, readiness and in-instance ROS participants

| Location | What it carries | Class |
|---|---|---|
| `D/runtime/container_campaign/stack_launch.py` (whole file) | `ContainerActStackLaunch`, `PushRosNamespace`, `SetRemap`, derived `namespace-config/*.yaml` | Remove |
| `W/src/so101_demo_py/launch/so101_mujoco_container_shard.launch.py` | Namespaced launch wrapper | Remove |
| `D/runtime/launch_composition/task_station.py:210,228-229`; `mujoco_actions.py:118-119,150-157` | `controller_parameters_path`/`plugin_parameters_path` overrides, only used for namespacing | Remove |
| `D/runtime/container_campaign/ros_namespace.py` (whole file) | Validation, `qualified_name`, `namespaced_parameters`, `namespace_remappings`, `container_ros_*init_options` | Remove; signal option moves to a neutral instance helper |
| `U/pick_place_startup_issuer.py:86-88` | Adds `--ros-namespace` for a `ContainerActStackLaunch` | Remove |
| `D/cli/act_stack_ready.py:48-57,176,182-185,200,284-286` | `graph_in_namespace`, `--ros-namespace`, endpoint qualification | Remove |
| `D/runtime/parallel_ros_ports/binding.py:43-59,68-76,79-83,111-121,145-150` | Namespace-aware node inventory, `worker_ros_namespace()` | Remove; inventory reverts to `/move_group/moveit` |
| `D/runtime/parallel_ros_ports/point_gate.py:92-95,125-126`; `observations.py:609-610` | Namespace passed to the gate and inventory | Remove |
| `D/runtime/parallel_ros_ports/execution.py:178-179` | Consumer-ready name `<ns>/so101_dynamic_cup_pick_place` | Fixed un-namespaced name |
| `parallel_ros_ports/isolated_node.py:158`, `execution.py:42`; `D/backends/mujoco/lifecycle.py:87`; `D/ros/dynamic_runtime.py:310,736`; `D/cli/scene_setup.py:45` | `rclpy.init(**container_ros_init_options())` | Revert to bare init |
| `D/ros/rgbd_snapshot.py:178`; `parallel_ros_ports/observations.py:154,533`; `perception.py:346` | `container_ros_global_init_options()` (namespace args plus signal NO) | Keep signal NO, keyed on the instance marker |
| `D/backends/mujoco/teleop_runtime.py:87-150` | `_RosScope` picks a private context when the namespace marker is set | Keep the private context, keyed on the instance marker; shared with teleop CLIs, so no unconditional change |
| `D/runtime/container_campaign/task_builder.py:78-79,110-114,218,281`; `collection_runtime.py:21-22` | Spec text fields, env drift, `controller_namespace`, borrowed-stack match | Drop namespace; domain compares to the constant |

### Stop, retirement and recorder

| Location | What it carries | Class |
|---|---|---|
| `D/runtime/container_campaign/controller_stop.py:26-29,70-74,81,139-158,185-194` | Namespaced isolated node; `ros_namespace` in the observation; `action_prefix == ns + lane` | Fixed lane names; remove field (schema bump) |
| `D/runtime/container_campaign/retirement.py:50-58,87-98,128-133,162,170-180,202-209` | `ros_namespace` constructor argument, "namespace changed" check, audit field, reader argument | Remove namespace; keep `ros_domain_id` and `session_id` |
| `D/act/offline/raw_recorder.py:273,284-295,306,314-321,333,348-349,449-453` | Topic map, namespaced probe, scoped recorder argv, namespace match | Remove; one recorder path |
| `raw_recorder.py:274,288,485-510` | `bag_root` evidence | Keep, re-keyed |
| `D/act/offline/container_bag_topics.py:17-22,53-113` | Topic-map write, read and validate; `logical_channel_map` | Remove |
| `container_bag_topics.py:25-50` | `bag_root_decision` (fixed output mount proof) | Keep; move to a neutral module |
| `D/act/offline/bag_io.py:6,21,39`; `replay.py:184-193` | Logical-name mapping on read and replay | Remove |
| `W/src/so101_mujoco_support/src/act_scoped_bag_record.cpp`; `CMakeLists.txt:35-40` | C++ recorder that requires the namespace marker (lines 34-39, 70-74, 84-86) | Remove |

### Admission store and qualification

| Location | What it carries | Class |
|---|---|---|
| `U/worker_slots.py:14-16,23-27,57-60,71-73` | Slot fields; `ROS_DOMAIN_SHARED`, `ROS_NAMESPACE_SHARED`, `ROS_CONTROLLER_SHARED`; 8-column insert | Slot becomes `(campaign_id, worker_id, execution_generation)` |
| `U/intent_store.py:145-158` | Table columns and three partial unique indexes | Schema v2 (section E) |
| `U/admission.py:562-575,588-591,845` | Slot schema check; cross-check against native children; cleanup compares registry domain/namespace to slot | Simplify; replace 588-591 with a native-instance exclusivity rule |
| `D/runtime/container_campaign/result_verifier.py`, `provenance.py`; `D/act/parallel_qualification_verifier.py`, `collection_qualification_recompute.py`; `D/cli/act_build_parallel_qualification_report.py`, `act_verify_parallel_qualification.py` | No domain/namespace field (grep empty). Recompute reaches them only through `registry.all_terminated` (`collection_qualification_recompute.py:407`) | Keep; follows the registry change |
| `W/src/so101_demo_py/config/mujoco/parallel_batch_act_offline.yaml:4-5` | `max_worker_count`, `ros_domain_ids` | Keep byte-identical; the ACT path stops reading them |

### Tests

- **Delete:** `X/runtime/container_campaign/test_python_ros_namespace.py`, `test_ros_namespace.py`, `test_stack_launch.py`; `X/act/offline/test_container_bag_topics.py`.
- **Rewrite:** `X/runtime/container_campaign/test_launch.py`, `test_launch_registry.py`, `test_shard_launcher.py`, `test_shard_owner.py`, `test_shard_owner_stop.py`, `test_shard_retirement.py`, `test_controller_stop.py`, `test_task_builder.py`, `test_task_builder_ready_check.py`, `test_collection_runtime.py`, `test_owner.py`, `test_case_inputs.py`, `test_task_commit_readback.py`.
- **Rewrite (other):** `X/cli/test_campaign_shard.py`, `test_container_task_campaign_integration.py`, `test_act_stack_ready.py`; `X/act/offline/test_container_bag_root.py`, `test_raw_bag_recorder.py`, `test_offline_recording_switch.py`; `X/backends/mujoco/test_teleop_runtime_contexts.py`; `X/runtime/test_parallel_ros_runtime_gate.py`, `test_parallel_ros_runtime_pose_publication.py`; `X/support/collection_qualification_world.py`.
- **Rewrite (teleop):** `W/src/so101_teleop/test/unified/test_worker_slots.py`, `test_act_campaign_admission.py`, `test_container_collection_admission.py`, `test_container_child_ownership.py`.

## B. What "fixed" should be

### What the native single worker uses today

- PROVEN from `REG/experiments/nonhead-first-episode-38cf0f8a-6448-48df-8287-7003ec11512a/run/resource_manifest.json`: `ROS_DOMAIN_ID` 181 and worker `worker-01`. `controller_namespace` is `/parallel/worker-01`, but that is only a label and env var; no topic is prefixed.
- PROVEN from `D/runtime/act_diagnostic_episode_station.py:22,78-85`: the stack is `so101_mujoco_act.launch.py`, root namespace.
- PROVEN from `run.log` in that directory: the run goes through `ProductionBatchComposition` with a Docker perception broker image.

### Proposed fixed identity (one constants module used by both launchers)

- `ROS_DOMAIN_ID=181`. This equals the native value, equals w00 in EXP-581 (`REG/act-w1-20261013T035415Z/shard-wave-0-w00-g1.json`), and is the first frozen contract value.
- No `ROS_NAMESPACE`; namespace is `/`.
- Stack is `so101_mujoco_act_execution_stack.launch.py` through `U/act_stack.py:28-62`. PROVEN: the container launch is only a namespacing wrapper around the same `_configured_act_execution_stack_actions` (`stack_launch.py:58-61`).
- Controller, action and node names as in `act_stack_ready.py:14-24` and `binding.py:31-41,55-60`.
- Environment: `ROS_LOCALHOST_ONLY=1`, `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`, `MUJOCO_GL=egl`.

### What stays unique per instance (recommended)

These are Host-assigned identities delivered through the spec, not ROS names:
- `worker_id`, `launch_generation`, `runtime_id`, `service_token`, container name, owned root, `task_id`.
- `simulation_session_id`. PROVEN: it is a plugin parameter stamped into every evidence message (`W/src/so101_mujoco_support/src/simulation_evidence_plugin.cpp:74-76`), fences reset receipts, and backs the registry's session-reuse rule (`registry.py:135`).
- `worker_id` and generation also fence requests on the shared Teacher service (`task_builder.py:435,586`), so they cannot be fixed.

### Is container isolation sufficient for DDS?

- PROVEN config: `--network none --ipc private --read-only` (`launch.py:132-134`). Live `docker inspect` of an EXP-582 shard: `NetworkMode=none`, `IpcMode=private`, `ShmSize=67108864`, `ReadonlyRootfs=true`, PID mode default (private).
- PROVEN: no `RMW_IMPLEMENTATION` or Fast DDS profile is set anywhere in the launch env, Dockerfiles or bootstrap.
- INFERRED: Jazzy defaults to `rmw_fastrtps_cpp` with UDPv4 plus shared-memory transport. Both are namespace-scoped: loopback lives in the private network namespace, and the port-named segments and locks live in the private `/dev/shm`. Two containers on the same domain and names therefore cannot discover each other.

Unproven; a real two-container run must confirm:
1. The base image does not set another RMW.
2. Two containers on domain 181 with identical names show zero cross-talk: each node list contains only its own nodes, session ids never mix in evidence, and action status is not seen across containers.
3. The 64 MB `/dev/shm` is adequate. The ledger (CP-3630) flags it as unexamined in connection with the EXP-580 burst loss.
4. Stock `ros2 bag record` works inside the container; every container run so far used the scoped C++ recorder.
5. The stop-time graph probe (`U/act_stack_probes.py:73-84`) sees only its own container.

**Host caveat.** A native instance has no isolation: it shares host loopback and `/dev/shm` with any other domain-181 participant, including native batch `worker-01`. Admission must therefore enforce native exclusivity.

## C. Requirement 2: the two code paths today

| | Container path | Native path (`act_diagnostic_episode run`) |
|---|---|---|
| Entry | `D/cli/act_collect_parallel.py` → `ContainerCampaignOwner` → `docker run campaign_shard` | `D/cli/act_diagnostic_episode.py:569-772` → `ProductionBatchComposition` (`worker_count=1`, line 643) |
| Control | Four-operation one-way control; local lease (`task_builder.py:178-184`); `ContainerTaskExecutor` + `CollectionTaskExecution` | Coordinator RPC with leases, ACKs and heartbeats; `ParallelWorker` (`D/cli/mujoco_batch/worker_process.py:268-412`) |
| Runtime class | `ContainerCollectionRuntime(ActWorkerRuntime(ParallelWorkerRuntime))` | `ParallelWorkerRuntime` |
| Ports | `ActRosRuntimePorts` | `ParallelRosRuntimePorts` |
| Stack | One long-lived stack owned by the shard and borrowed per task (`collection_runtime.py:60-70`) | Worker launches its own station per run (`D/runtime/parallel_worker_runtime.py:286-292`) |
| Perception | `ActTeacherClient` → Teacher inference container; `ActFixedCollectionWorkload` | `_WorkerBrokerProxy` → perception Broker image |
| Mode | `formal` only (`task_builder.py:153`) | `preselected_target_diagnostic` only (`act_diagnostic_episode_station.py:40`) |
| Artifacts | `CollectionCaseArtifacts`, `/act/output/tasks/<task_id>/` | `_ArtifactResults`, `run/workers/worker-01/attempts/…` |
| Admission | Unified store: slots plus GPU lease | Start guard only |

- **Shared today:** the `ParallelWorkerRuntime` mixins (reset, initial gate, recorder, offline processing, QC, seal), the port mixins, the raw recorder and the offline pipeline.
- **Why they diverge:** the native path predates the one-way design and still uses the Coordinator protocol and Broker. The marker branches inside the shared layer exist only for namespacing.
- PROVEN: `ActWorkerRuntime`, `ActRosRuntimePorts`, `ActTeacherClient` and `ContainerCollectionRuntime` have no native caller.
- PROVEN stale: `D/cli/act_collect.py:51` calls `service.start(payload, planned)`, but the real signature is `start(spec, *, allow_existing)` (`U/admission.py:679`).
- INFERRED: the `act_diagnostic_episode` admission kind (`admission.py:251`) has no caller in `D`.

### Target structure

1. **One instance program**, `D/runtime/act_instance/` (new):
   - `identity.py` holds the constants and env builder.
   - `layout.py` holds an `InstanceLayout` with `owned_root`, `output_root`, `control_root`, `teacher_socket`, `install_prefix`.
   - `program.py` holds `run_instance(spec, runtime_config, layout)`, which is today's `run_shard`, `serve_shard` and `compose_stack` with the layout injected.
   - `task_builder.py`, `collection_runtime.py`, `task_executor.py`, `controller_stop.py`, `retirement.py`, `case_artifacts.py`, `task_contracts.py` and `task_results.py` move with it.
2. **Container shell**: `campaign_shard` only checks pid 1, `/act/venv/bin/python` and `/act/install`, builds the fixed layout (`/act/output`, `/act/control`, `/act/ipc/teacher/inference.sock`) and calls `run_instance`.
3. **Native shell**: a new `act_instance_native` entry builds the layout from the owned root with `output_root=<owned_root>/output`, sets the same env and calls the same `run_instance`.
4. **Host side unchanged** apart from a launcher choice. `NativeInstanceOwner` gets the same surface as `ContainerShardOwner` (`start`, `check_health`, `control_client`, `close`, `prove_stopped`, `instance_exit`), built on the existing process-owner primitives in `U/bridge.py` and `so101_teleop.owned_group`.

### What a native single-worker run looks like afterwards

- `act_collect_parallel … --worker-count 1 --qualification --instance-launcher native`.
- Same admission (GPU lease, slot w00), Teacher service container, coordinator, wave verifier and commit.
- Same layout: `<run>/wave-0/w00/g1/{control,output/tasks/<task_id>,stack,retirement,…}`.
- Admission refuses `native` with `worker_count != 1`, and refuses a second active native instance on the host.

Known implementation points (PROVEN):
- `ContainerChildIpcServer.start` refuses socket paths over 103 bytes (`U/child_runtime.py:329-333`), and `<owned_root>/control/normal.sock` under `REG` exceeds that. The native layout needs a short private control directory (the `D/runtime/unix_address.py` strategy) or a dirfd bind.
- `ContainerBridgeProcessOwner.accept_ready` requires a PID namespace different from the Host's (`bridge.py:648-651`). The native owner needs its own ready acceptance.
- The Teacher socket path is hard-coded in `coordinator.py:175` and `task_builder.py:140`; it has to come from the layout.

## D. Requirement 3: non-container multi-worker inventory

PROVEN: there is no native ACT Teacher collection with more than one worker. `act_collect_parallel` is container-only, and `act_diagnostic_episode run` hard-codes one worker.

### Removed with the old native ACT path (verify each by grep at implementation)

- `act_diagnostic_episode run` (`act_diagnostic_episode.py:538-772`) and its helpers.
- `D/runtime/act_diagnostic_episode_station.py` and its hook at `parallel_worker_runtime.py:169-175`.
- ACT fields in the native worker spec (`worker_process.py:279,293-362`) and the collection branch of `_ArtifactResults` (`worker_process.py:44-63,74,107-125`).
- The ACT inputs-launch arguments in `task_station.py:55-97` and `so101_mujoco_act.launch.py`.
- The `workload` port in `D/parallel_batch/worker.py:81-87`. INFERRED dead natively: `_build_worker_from_spec` never passes it.
- `D/cli/act_collect.py` (stale) and the `act_diagnostic_episode` admission kind.

### Still needed

- **By the container campaign:** `act_diagnostic_episode inspect/prepare/preflight/qc` and `diagnostic_episode_inputs`; `ParallelWorkerRuntime` and the port mixins; `LeaseIdentity`, `WorkerResources`, `WorkerProtocol._gate_summary`; `_load_runtime_config`.
- **By non-ACT features (must not break):**
  - The whole native batch: Coordinator, Broker, leases, adaptive pool (`D/parallel_batch/*`, `D/cli/mujoco_batch/*`, `so101_parallel_batch`, `so101_parallel_batch_cleanup`, `W/scripts/run_so101_adaptive_batch.zsh`).
  - Web Expert Validation, which consumes it (`W/src/so101_teleop/so101_teleop/expert_validation/production_service/restore.py:86-140`, `layout.py:174`).
  - The macOS single and two-worker campaigns.
  - `ActChildLaunch`/`ActChildRegistry` for pick-place validation (`bridge.py:98-145`).
  - `_RosScope`, `transactional_reset` and `current_evidence`, used by `D/cli/teleop_reset.py:59`, `teleop_workflow.py:144` and `D/runtime/task_batch_runtime.py:522`.

Whether requirement 3 also reaches the non-ACT native batch is open question Q1.

## E. Admission store and frozen identities

**Slots remain** as w00..w07, representing container instances. The key is already `(campaign_id, worker_id, execution_generation)` (`intent_store.py:153`).

**Existing store** `REG/unified/intents.sqlite3`, read with `immutable=1` (WAL content not included):
- `schema_version` is 1, with the three partial unique indexes present.
- Six inactive rows, all on domain 181.
- State `IDLE`, zero GPU leases.

PROVEN consequence: with one fixed domain, the second slot of any two-worker campaign would violate `act_active_slot_domain`. `CREATE TABLE IF NOT EXISTS` will not alter the table, and the code has no migration mechanism.

**Recommended migration (v1 → v2)**, on open, in one immediate transaction:
- Require state IDLE, zero active slots and zero GPU leases.
- Rename `act_worker_slots` to `act_worker_slots_v1` so the audit rows survive unchanged.
- Drop the three indexes and create the new five-column table.
- Set `schema_version` to 2.
- Beforehand, back up the three store files with sha256 under the evidence root.

**New rule:** at most one active native instance per host, replacing `admission.py:588-591`. The store is shared with Expert Validation, so only the ACT tables are touched.

**Identities that do not change** (if the YAML stays untouched):
- `runtime_config_sha256` 5775cb3b…
- `collection_config_sha256` 614bbc0d…
- Contact policy fingerprint, manifests, campaign-config schema, the `ParallelRuntimeConfigLinuxCuda` contract.

**Identities that change:**
- Source commit, both image digests, `package_source_sha256` and `install_sha256`.
- Shard spec schema, launch registry JSON, slot JSON.
- `runtime-ready.json`, controller-stop observation and retirement audit schemas.
- Bag channel names, absence of the topic-map file, the recorder executable.
- `domain_session_map_sha256` changes per admission only (`admission.py:790-794`).

**Comparability of EXP-581:**
- INFERRED comparable at the sealed-episode level: simulator, controllers, parameter values, scene and policies are identical, and episodes were built from logical channel names.
- Not preserved: once `logical_channel_map` is removed, new code cannot re-read the raw bags of EXP-576..582. They remain readable at commit 64aca49d5 and its retained images.
- Under the 2026-09-30 design §7, a controlled topology change means W1/W2 must be redone in new run roots. EXP-581/582 stay as history and are not spliced.
- No qualification report exists yet, so none is invalidated.

## F. Container-only fixes: dead versus still relevant

**Dead; remove with tests:**
- Topic map and `logical_channel_map`.
- The scoped C++ recorder.
- Namespace-aware node inventory, including the `<ns>/moveit` rule.
- Namespaced lane and action prefixes; the namespaced consumer-ready name.
- `namespace_remappings` and `namespaced_parameters`; the `--ros-namespace` readiness option and `graph_in_namespace`.
- `CONTAINER_ROS_NAMESPACE_DRIFT` and `CONTAINER_BAG_NAMESPACE_DRIFT`.

**Still relevant:**
- Step-grid simulator time (submodule) and the stale-join re-baseline.
- numpy uuid acceptance (`controller_stop.py:32-36`) and concurrent lane polling.
- Formal coverage predicate.
- Receiver-lag suspension (`D/adapters/act/ros_episode_physics.py:57-64`).
- Private rclpy context for reset and evidence, and `SignalHandlerOptions.NO`; both re-keyed to the instance marker.
- `bag_root_decision`, the repeatable ready check, the physics hold release on retire, and the nvidia EGL vendor file.

## 1. Design-change statement (amends the 2026-09-30 design)

Replaces the first sentence of §2 paragraph 3 (line 44):

> Each shard container runs the single-worker ACT instance program with a fixed ROS identity: domain 181, root namespace, and the un-namespaced node, topic, service, action and controller names of `so101_mujoco_act_execution_stack.launch.py`. Shards are isolated from each other and from the Host only by the container: private network namespace (`--network none`), private IPC and `/dev/shm` (`--ipc private`), private PID namespace, localhost-only discovery. Each instance still exclusively owns its MuJoCo session id, controller processes, Recorder, temp directory and evidence directory; the Host assigns the unique identities (`worker_id`, launch generation, session id, runtime id, token, container name, owned root, `task_id`). A non-container run executes the same instance program with the same fixed identity for exactly one worker, admitted through the same unified entry.

Consequential edits:
- §4 and §5: replace the "Domain" cleanup wording with "container".
- §8 step 3: add "two containers with identical domain and names show no cross-talk".

Non-goals:
- No change to observation/action, 10 Hz sampling, Task 8 safety, thresholds, QC rules or Teacher policy.
- No change to the runtime YAML or its contract.
- No change to the one-way control protocol or the fixed `/act/output` rule.
- No Docker resource limits or shm sizing (measured, not changed).
- No real-hardware scope; no compatibility reader for old namespaced bags.
- No native multi-worker.

## 2. Open questions for the human

1. **Scope of requirement 3.** Does it cover only ACT Teacher collection, or also the non-ACT native batch (Expert Validation adaptive pool, `so101_parallel_batch`, macOS two-worker)? Recommendation: ACT only; deleting the rest removes a working product feature unrelated to this change.
2. **Shape of the native run.** Same Host campaign owner with a native launcher and the Teacher service still in its container, or a standalone local driver without admission? Recommendation: the former. Admission is the only thing preventing a domain-181 collision on the Host. The cost is a new Host owner with its own stop proof.
3. **`act_diagnostic_episode run`.** It is the only path with `preselected_target_diagnostic` mode, Teacher failure injection, the fault sandbox and `--collection off`. Recommendation: remove it after the native instance run is verified and do not port those features now. Keep `verify-commit`, `check-export` and `readback` as read-only tools for historical runs.
4. **Store migration.** May the registered `REG/unified/intents.sqlite3` be migrated in place to schema v2, with a hashed backup and the old rows kept in `act_worker_slots_v1`? Recommendation: yes; a fresh store would restart execution generations.
5. **Old bags.** Is it acceptable that EXP-576..582 raw bags are re-readable only at commit 64aca49d5? Recommendation: yes; they are functional-plane, never exportable, and the removal rule applies.
6. **Fixed values.** Confirm domain 181, per-instance unique session id, and the runtime YAML left byte-identical. Recommendation: confirm all three.

## 3. Implementation plan

Single writer, RED then GREEN per task. Entry gate: EXP-582 settled and recorded, questions answered, this amendment and plan committed as docs.

**Task 1 — Instance identity and marker (additive).**
- New files: `D/runtime/act_instance/identity.py` (domain, env builder, `SO101_ACT_INSTANCE_ROOT` marker) and `D/ros/process_init.py` (signal options helper).
- Re-key `_RosScope` (`teleop_runtime.py:99`), the four global-init sites and the `raw_recorder.py` bag-root logic on the instance marker.
- Move `bag_root_decision` to `D/act/offline/bag_root.py`.
- Tests: new `X/runtime/act_instance/test_identity.py`; rewrite `test_teleop_runtime_contexts.py` and `test_container_bag_root.py`.
- RED case: marker set and no namespace gives a private context, signal NO, a bag-root decision, and no `-r __ns` arguments.

**Task 2 — Flip the shard to the fixed identity.**
- Files: `campaign_shard.py`, `launch.py`, `shard_launcher.py`, `shard_owner.py`, `owner.py`, `registry.py`, `retirement.py`, `controller_stop.py`, `task_builder.py`, `collection_runtime.py`, `act_fixed_collection_composition.py`, `U/bridge.py` (`ContainerBridgeProcessOwner`), `U/pick_place_startup_issuer.py:86-88`.
- Spec `schema_version` 2 without the two fields; the shard builds a plain `ActStackLaunch`; the slot's domain and namespace are ignored for now.
- Tests: the rewrite list from section A for these modules, plus `test_container_task_campaign_integration.py`.
- RED cases: argv has `ROS_DOMAIN_ID=181` and no `ROS_NAMESPACE`; a spec carrying `ros_namespace` is refused; two live shard launches no longer collide.

**Task 3 — Slots and store.**
- Files: `U/worker_slots.py`, `U/intent_store.py` (v2 plus migration), `U/admission.py:562-575,588-591,845`, composition slot build.
- Tests: `test_worker_slots.py`, `test_act_campaign_admission.py`, `test_container_collection_admission.py`, and a new migration test on a copy of a v1 fixture.
- RED cases: two active slots in one campaign are accepted; a v1 store with an active slot refuses migration.

**Checkpoint A — real container W1, eight scenes**, on rebuilt images, with the dead namespace code still present.

**Task 4 — Remove namespace code.**
- Delete `ros_namespace.py`, `stack_launch.py`, the container shard launch file, `container_bag_topics.py`, `act_scoped_bag_record.cpp` and its CMake lines.
- Remove the parameter-path overrides, the `binding.py` namespace parameters, the `point_gate.py`/`observations.py`/`execution.py` namespace uses, the `act_stack_ready.py` namespace option, the `bag_io.py`/`replay.py` mapping, and all remaining `container_ros_*` call sites.
- Delete the four test files listed in section A and adjust the rest.
- RED: a source-tree test that greps for the removed symbols and fails while any remain.

**Task 5 — Extract the instance program.**
- Create `InstanceLayout` and `run_instance`; reduce `campaign_shard` to the container shell; take the Teacher socket and output root from the layout (`coordinator.py:175`, `task_builder.py:140`).
- Tests: `test_campaign_shard.py`; new `X/runtime/act_instance/test_program.py` running the same program under both layouts with doubles.

**Task 6 — Native launcher.**
- Add `NativeInstanceOwner`, the `act_instance_native` entry, `--instance-launcher`, the native exclusivity rule and worker-count-1 rule in admission, and a short control socket directory.
- Tests: an owner lifecycle and stop-proof suite mirroring `test_shard_owner*.py`, admission negatives, CLI preflight.

**Checkpoint B — real native single-worker run, eight scenes.**

**Task 7 — Remove the old native ACT path** (the removal list in section D, per Q3).
- Update `test_diagnostic_episode_station_selection.py`, `X/act/test_act_collection.py` and the native worker-spec tests.
- Update `W/docs/guides/so101-act-head-wrist-rgb.md` (it mentions `act_collect` at line 23), using the project humanizer skill.

**Task 8 — Freeze and verify** (section 4); ledger checkpoints throughout.

## 4. Verification plan

- **Targeted tests:** per task, RED then GREEN; serial runs are for diagnosis only.
- **Host gates on the final commit:**
  - Fresh colcon build.
  - `so101_demo_py` ordinary gate (`test/` only) with xdist at `min(8, CPUs)`.
  - The other packages, including `so101_teleop` and `so101_mujoco_support`.
  - Scratch under `REG/scratch/<id>/tmp` with `tempfile` verified, per AGENTS.md.
  - Baseline to compare against: CP-3630, 12666 passed, 0 failed, 167 skipped.
- **Images:** rebuild shard and inference; read back provenance; confirm `act_scoped_bag_record` is absent and `ros2 bag record` is present; record `RMW_IMPLEMENTATION` and the installed `librmw_*` libraries (closes the first unproven item in section B).
- **Store:** hashed backup, migration, read back the schema and `act_worker_slots_v1`.

Real runs, each in a new run root:
1. **Container, one worker, eight scenes.** Must prove:
   - Env is domain 181 with no namespace.
   - Node inventory matches the native rules.
   - Bags hold logical names with no map file; stock recorder starts and closes with `transport_lost` reported.
   - 8/8 sealed and wave verified; stop proven; slot released.
2. **Native, one worker, same scenes and same program.** Must prove:
   - Same artifacts and schema as run 1 apart from layout paths; same instance program hash.
   - Admission holds the native reservation.
   - Process-group stop proof; Host graph clear on domain 181.
   - A second native start is refused.
3. **Two containers concurrently.** Must prove:
   - Both on domain 181 with identical names; each node list holds only its own nodes.
   - No foreign session id in any evidence or bag.
   - Per-container `/dev/shm` usage recorded against the 64 MB limit.
   - RTF and loss reported; both stops proven; both slots released.

W8 qualification follows the existing plan, unchanged.

## 5. Risks and what could invalidate existing evidence

- **Editing during a live run.** Changing worktree files bound by a running campaign's hashes can fail that run.
- **Native Host instance has no isolation.** It depends entirely on admission exclusivity. On a multi-GPU host the GPU lease alone would not provide it (INFERRED from the lease primary key), hence the explicit native reservation.
- **Recorder change.** No container run has used stock `ros2 bag record`. If it misbehaves, the fallback is a namespace-free C++ recorder used by both launchers, never a per-launcher split.
- **Shared-code regressions.** `_RosScope`, the port mixins and the launch composition are shared with teleop, Expert Validation and pick-place validation; re-keying on an explicit marker limits the blast radius. The `so101_teleop` gate is mandatory.
- **Store migration.** It modifies a registered evidence file; without the backup and authorization it must not run.
- **Evidence continuity.** EXP-576..582 raw bags and stop audits become unreadable by new code; W1/W2 results on the old topology cannot be counted for the new one.
- **Shared memory.** Identically named Fast DDS segments are safe only while `--ipc private` holds; any future `--ipc host` or shared `/dev/shm` mount would silently merge all shards. Add a launch-argv test pinning both flags.
- **Removal reach.** The native ACT hooks interleave with generic batch code used by Expert Validation; each deletion needs a reference check and the `so101_teleop` gate.

### Critical Files for Implementation
- `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a/src/so101_demo_py/src/cli/campaign_shard.py`
- `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a/src/so101_demo_py/src/runtime/container_campaign/ros_namespace.py`
- `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a/src/so101_demo_py/src/runtime/container_campaign/task_builder.py`
- `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a/src/so101_demo_py/src/act/offline/raw_recorder.py`
- `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a/src/so101_teleop/so101_teleop/unified/intent_store.py`
