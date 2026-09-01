task_id: so101-yolo-docker-inference-20260901
goal: macOS 使用宿主机 MPS，Linux 使用 launch 启动的 CUDA Docker 容器执行同一 YOLO-Seg 推理入口
success_contract: launch contract tests prove both platform branches; the pinned amd64 image builds and imports ROS, CUDA PyTorch, Ultralytics, Open3D, and rgbd_object_pose
worktree: /Users/matianyi/.codex/worktrees/78474e78-2991-4c4b-9d35-ac0495fbd06b/moveit-demo
branch: DETACHED
base_commit: 9c8a90b87ad60be281199dbeb038c2cdf581de6c
current_commit: 9c8a90b87ad60be281199dbeb038c2cdf581de6c
evidence_root: /tmp/so101-debug-yolo-docker-inference-20260901
confirmed_conclusions:
  - EXP-001 proved the previous launch contract had no runtime selector or Linux Docker process
  - EXP-002 proved the launch contract selects host Node for explicit host use and a CUDA Docker ExecuteProcess for Linux auto
  - EXP-003 proved the reusable build wrapper emits the pinned amd64 Docker build contract
  - EXP-005 proved ai-station can run Docker builds but cannot reach Docker Hub directly; the pinned DaoCloud mirror manifest is reachable
  - EXP-006 proved the mirrored image and all pinned dependencies install; the build-time ROS import must use ros_entrypoint.sh
  - EXP-007 built the pinned Linux amd64 image successfully on ai-station
  - EXP-008 proved the image entrypoint, ROS imports, pinned model dependencies, and CUDA tensor execution on ai-station
disproven_routes:
  - Local Docker Desktop is not an authorized ROS Jazzy build or runtime target
open_hypotheses:
  - NONE
latest_checkpoint: CP-003
next_experiment: NONE

correction: The ledger was created after EXP-001 through EXP-003. Their hypotheses and commands were already frozen in the TDD tests and commentary, and the original outputs remain under the registered evidence root. This correction records the late ledger creation without rewriting those results.

experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: The current launch lacks the agreed platform runtime split
prediction: New launch tests fail because perception_runtime and Linux Docker action do not exist
single_variable: Add tests only; production code remains unchanged
lifecycle: ISOLATED_STACK
preconditions:
  - No MuJoCo, MoveIt, or robot workflow is started
success_criteria:
  - Existing tests pass while the new runtime declarations and Linux Docker test fail for the missing feature
failure_criteria:
  - New tests pass against unchanged production code
invalid_criteria:
  - Test collection fails before launch_composition loads
provenance:
  source_commit: 9c8a90b87ad60be281199dbeb038c2cdf581de6c
  install_overlay: /tmp/so101-debug-yolo-docker-inference-20260901/ament
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: 191
  gz_partition: NONE
commands:
  - command: PYTHONNOUSERSITE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_perception_pick_place_launch.py -q
    exit_code: 1
observed:
  - OBSERVED 49 existing tests passed and 2 new tests failed at the missing perception_runtime/platform symbols
inferred:
  - The regression tests reached the intended launch boundary
conclusion: RED confirmed
evidence:
  - /tmp/so101-debug-yolo-docker-inference-20260901/red-launch-test.txt
decision: KEEP
next_experiment: EXP-002

experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: A platform resolver plus ExecuteProcess docker run action can preserve the host path and satisfy Linux CUDA launch composition
prediction: All perception launch contract tests pass with exact ROS env, GPU, host network, read-only weights, and writable evidence mounts
single_variable: Implement the launch runtime split
lifecycle: ISOLATED_STACK
preconditions:
  - No Docker container or robot stack is started by the contract test
success_criteria:
  - All tests in test_perception_pick_place_launch.py pass
failure_criteria:
  - Any existing launch behavior or new Docker command assertion fails
invalid_criteria:
  - Source package or ROS launch cannot be imported
provenance:
  source_commit: 9c8a90b87ad60be281199dbeb038c2cdf581de6c
  install_overlay: /tmp/so101-debug-yolo-docker-inference-20260901/ament
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: 191
  gz_partition: NONE
commands:
  - command: PYTHONNOUSERSITE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_perception_pick_place_launch.py -q
    exit_code: 0
observed:
  - OBSERVED 51 tests passed; Linux auto emitted one Docker ExecuteProcess and explicit host use emitted one rgbd_object_pose Node
inferred:
  - Launch composition preserves color_geometry and host inference while adding the Linux container boundary
conclusion: GREEN confirmed at the launch contract layer
evidence:
  - /tmp/so101-debug-yolo-docker-inference-20260901/green-launch-test.txt
decision: KEEP
next_experiment: EXP-003

experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: A repository build wrapper can make the inference image reproducible without embedding host-specific paths
prediction: The fake Docker boundary receives the pinned Dockerfile, linux/amd64 platform, explicit image tag, and repository context
single_variable: Add the inference image build wrapper and its contract test
lifecycle: ISOLATED_STACK
preconditions:
  - Docker is replaced by a task-owned fake executable
success_criteria:
  - The wrapper test passes with an exact argument list
failure_criteria:
  - The wrapper omits platform, Dockerfile, tag, or repository context
invalid_criteria:
  - The fake executable is not first on PATH
provenance:
  source_commit: 9c8a90b87ad60be281199dbeb038c2cdf581de6c
  install_overlay: NONE
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: 191
  gz_partition: NONE
commands:
  - command: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_yolo_inference_container.py -q
    exit_code: 0
observed:
  - OBSERVED 1 test passed after the missing-script RED failure
inferred:
  - The image build invocation is reusable and independent of the current shell directory
conclusion: Build wrapper contract passed
evidence:
  - /tmp/so101-debug-yolo-docker-inference-20260901/red-container-test.txt
  - /tmp/so101-debug-yolo-docker-inference-20260901/green-container-test.txt
decision: KEEP
next_experiment: EXP-004

experiment_id: EXP-004
status: INVALID
prior_experiment: EXP-003
hypothesis: The pinned amd64 image closes ROS Jazzy, CUDA PyTorch, Ultralytics, Open3D, and package entrypoint dependencies
prediction: A local Docker Desktop amd64 build exits 0 and the Dockerfile import gate succeeds
single_variable: Replace the fake Docker boundary with a real local amd64 build
lifecycle: ISOLATED_STACK
preconditions:
  - Local Docker Desktop is linux/arm64 and uses amd64 emulation
  - No ROS graph or robot workflow is started
  - The rejected ai-station build did not start Docker or upload context
success_criteria:
  - Image build exits 0
  - Image config exposes /ros_entrypoint.sh rgbd_object_pose
  - Container import/version smoke exits 0
failure_criteria:
  - Any image layer or import gate fails with a reproducible dependency error
invalid_criteria:
  - Docker Desktop stops or network download is interrupted before a dependency conclusion is possible
provenance:
  source_commit: 9c8a90b87ad60be281199dbeb038c2cdf581de6c
  install_overlay: ros:jazzy-ros-base-noble@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4
  runtime_executable: /usr/local/bin/docker
  ros_domain_id: 191
  gz_partition: NONE
commands:
  - command: scripts/yolo-seg-inference-container.sh build --image so101-yolo11n-seg-inference:verification-platform-split
    exit_code: 130
observed:
  - OBSERVED the pinned ROS base layer completed and the apt dependency layer started
  - OBSERVED the user then disallowed running ROS Jazzy in local Docker; the build was immediately interrupted with SIGINT
inferred:
  - The interrupted local build cannot support an image or runtime conclusion
conclusion: INVALID by an explicit execution-location correction; no ROS container was run
evidence:
  - /tmp/so101-debug-yolo-docker-inference-20260901
decision: ABANDON
next_experiment: EXP-005

experiment_id: EXP-005
status: VALID
prior_experiment: EXP-004
hypothesis: The pinned image builds natively on the authorized ai-station Docker daemon and closes all inference dependencies
prediction: The remote native amd64 build exits 0, then image config and import/CUDA smoke checks exit 0
single_variable: Build location changes from local amd64 emulation to authorized ai-station native amd64 Docker
lifecycle: ISOLATED_STACK
preconditions:
  - User explicitly authorizes sending the repository build context to ai-station
  - ai-station Docker reports linux/amd64 29.1.3
  - No MuJoCo, MoveIt, or robot workflow is started
success_criteria:
  - Remote image build exits 0
  - Image entrypoint is /ros_entrypoint.sh rgbd_object_pose
  - ROS/model imports and CUDA tensor smoke exit 0
failure_criteria:
  - A reproducible image build, import, or CUDA error occurs
invalid_criteria:
  - SSH or Docker daemon connectivity fails before a dependency conclusion is possible
provenance:
  source_commit: 9c8a90b87ad60be281199dbeb038c2cdf581de6c
  install_overlay: ros:jazzy-ros-base-noble@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4
  runtime_executable: DOCKER_HOST=ssh://ai-station docker
  ros_domain_id: 191
  gz_partition: NONE
commands:
  - command: DOCKER_HOST=ssh://ai-station scripts/yolo-seg-inference-container.sh build --image so101-yolo11n-seg-inference:verification-platform-split
    exit_code: 1
  - command: ssh ai-station docker manifest inspect docker.m.daocloud.io/library/ros:jazzy-ros-base-noble@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4
    exit_code: 0
observed:
  - OBSERVED user authorization and ai-station linux/amd64 Docker provenance were confirmed before starting the build
  - OBSERVED Docker Hub manifest HEAD timed out before Dockerfile execution; direct curl timed out, no registry mirrors or proxy variables were configured, and the ROS base image was not cached
  - OBSERVED the same multi-platform manifest digest was readable through docker.m.daocloud.io and contained four manifests
inferred:
  - Docker Hub routing, not Dockerfile content or the Docker daemon, is the first failed boundary
conclusion: VALID environment failure; use the reachable mirror while retaining the exact official digest
evidence:
  - /tmp/so101-debug-yolo-docker-inference-20260901
decision: KEEP
next_experiment: EXP-006

experiment_id: EXP-006
status: VALID
prior_experiment: EXP-005
hypothesis: Replacing only the registry hostname with the reachable DaoCloud mirror while retaining the official digest allows the native amd64 build to reach Dockerfile dependency installation
prediction: The base image resolves by the same digest and the build advances past the FROM metadata boundary
single_variable: ROS base registry hostname changes from docker.io to docker.m.daocloud.io; tag and sha256 digest remain unchanged
lifecycle: ISOLATED_STACK
preconditions:
  - DaoCloud returned the same pinned OCI index digest on ai-station
  - No ROS or robot workflow is running for this experiment
success_criteria:
  - Build resolves the base image and exits 0 through all Dockerfile import gates
failure_criteria:
  - Build fails at a reproducible later dependency or import boundary
invalid_criteria:
  - Mirror connectivity fails before the pinned manifest resolves
provenance:
  source_commit: 9c8a90b87ad60be281199dbeb038c2cdf581de6c
  install_overlay: docker.m.daocloud.io/library/ros:jazzy-ros-base-noble@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4
  runtime_executable: DOCKER_HOST=ssh://ai-station docker
  ros_domain_id: 191
  gz_partition: NONE
commands:
  - command: DOCKER_HOST=ssh://ai-station scripts/yolo-seg-inference-container.sh build --image so101-yolo11n-seg-inference:verification-platform-split
    exit_code: 1
observed:
  - OBSERVED Dockerfile now uses the reachable mirror hostname and preserves the exact official OCI digest
  - OBSERVED the base, apt, Tsinghua dependencies, CUDA PyTorch, Ultralytics, and Open3D layers completed
  - OBSERVED the final build-time import failed only at rclpy because the direct venv Python command did not source /opt/ros/jazzy/setup.sh
inferred:
  - Runtime entrypoint path setup is absent only from the direct build smoke command
conclusion: VALID later-boundary failure; run the import smoke through /ros_entrypoint.sh
evidence:
  - /tmp/so101-debug-yolo-docker-inference-20260901
decision: KEEP
next_experiment: EXP-007

experiment_id: EXP-007
status: VALID
prior_experiment: EXP-006
hypothesis: Running the build-time import gate through the image's ROS entrypoint exposes rclpy and vision_msgs without changing model dependencies
prediction: Cached rebuild exits 0 and all version/import assertions pass
single_variable: Build-time import command changes from direct python to /ros_entrypoint.sh python
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-006 dependency layers are cached on ai-station
  - /ros_entrypoint.sh is supplied by the pinned ROS base image
success_criteria:
  - Image build exits 0 and writes the requested tag
failure_criteria:
  - A later import, version, or image export boundary fails reproducibly
invalid_criteria:
  - Cached layers are unavailable or network failure occurs before the modified import gate
provenance:
  source_commit: 9c8a90b87ad60be281199dbeb038c2cdf581de6c
  install_overlay: /opt/ros/jazzy/setup.sh in pinned ROS base image
  runtime_executable: /ros_entrypoint.sh python
  ros_domain_id: 191
  gz_partition: NONE
commands:
  - command: DOCKER_HOST=ssh://ai-station scripts/yolo-seg-inference-container.sh build --image so101-yolo11n-seg-inference:verification-platform-split
    exit_code: 0
observed:
  - The modified /ros_entrypoint.sh import gate passed for open3d, rclpy, torch, torchvision, ultralytics, and vision_msgs
  - Image manifest sha256 is 26f32411b4291915d13cd298efdb9f50641b70d7eb6607566ce5e5fcc2e2efae
  - Image config sha256 is a3e2c4775f2076d03f16714cc97e26c13aadc417c18220ee039b1205617a8e7d
  - The requested verification-platform-split tag was exported and unpacked on ai-station
inferred:
  - The pinned image is buildable on the intended Linux amd64 Docker host
conclusion: VALID
evidence:
  - /tmp/so101-debug-yolo-docker-inference-20260901
decision: KEEP
next_experiment: EXP-008

experiment_id: EXP-008
status: VALID
prior_experiment: EXP-007
hypothesis: The built image preserves the intended ROS CLI entrypoint and can execute CUDA work on ai-station without starting the perception node
prediction: Image inspection reports /ros_entrypoint.sh rgbd_object_pose, imports pass, torch reports CUDA available, and a CUDA tensor operation succeeds
single_variable: Execute runtime smoke checks against the completed image
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-007 image exists on ai-station
  - ai-station exposes an NVIDIA GPU to Docker
success_criteria:
  - Image entrypoint and command match the Dockerfile contract
  - Container import and CUDA tensor assertions exit 0
failure_criteria:
  - Image configuration drifts or CUDA/import assertions fail reproducibly
invalid_criteria:
  - ai-station GPU or Docker daemon becomes unavailable during the smoke test
provenance:
  source_commit: 9c8a90b87ad60be281199dbeb038c2cdf581de6c
  install_overlay: /opt/ros/jazzy/setup.sh in completed image
  runtime_executable: /ros_entrypoint.sh python
  ros_domain_id: 191
  gz_partition: NONE
commands:
  - command: Inspect image entrypoint and run import/CUDA tensor smoke on ai-station
    exit_code: 0
observed:
  - Image entrypoint is ["/ros_entrypoint.sh", "rgbd_object_pose"] and the image has no separate Cmd
  - Runtime imports report torch 2.13.0+cu130, torchvision 0.28.0+cu130, ultralytics 8.4.115, and open3d 0.19.0
  - torch.cuda.is_available() is true for NVIDIA GeForce RTX 5080
  - A CUDA tensor computation returned the expected sum 12.0
inferred:
  - The image is ready for launch-driven CUDA inference on ai-station
conclusion: VALID
evidence:
  - /tmp/so101-debug-yolo-docker-inference-20260901
decision: KEEP
next_experiment: EXP-009

experiment_id: EXP-009
status: INVALID
prior_experiment: EXP-008
hypothesis: The platform split and container additions preserve the package's existing source-level behavior
prediction: The complete so101_demo_py pytest suite, Python compilation, shell syntax, and diff checks pass
single_variable: Run the complete local source verification suite without Docker execution
lifecycle: ISOLATED_STACK
preconditions:
  - Task-owned Python target contains the current source package
  - The macOS ROS Jazzy overlay is sourced only for Python test imports
success_criteria:
  - Full package pytest suite exits 0
  - Python compileall, shell syntax, and diff checks exit 0
failure_criteria:
  - A reproducible test, syntax, or whitespace regression occurs
invalid_criteria:
  - The local test overlay cannot be constructed from current source
provenance:
  source_commit: 9c8a90b87ad60be281199dbeb038c2cdf581de6c
  install_overlay: task-owned colcon install over /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/setup.zsh
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: 191
  gz_partition: NONE
commands:
  - command: Build task-owned isolated so101_demo_py install
    exit_code: 0
  - command: Run complete src/so101_demo_py/test suite
    exit_code: 1
  - command: Run platform-contract tests
    exit_code: 0
  - command: Run compileall, shell syntax, and git diff checks
    exit_code: 0
observed:
  - The isolated so101_demo_py colcon build completed
  - The complete package run reported 903 passed and 4 failed
  - All 4 failures require third_party/mujoco_ros2_control content, which is not initialized in this Codex worktree
  - The task-scoped launch, image-wrapper, and package-identity suite reported 57 passed
  - Python compileall, both container-script syntax checks, and git diff --check passed
inferred:
  - The 4 full-suite failures are worktree fixture gaps rather than regressions in the platform split
conclusion: INVALID for the complete-suite success criterion because the pinned submodule is absent; task-scoped regression evidence is valid
evidence:
  - /tmp/so101-debug-yolo-docker-inference-20260901
decision: KEEP
next_experiment: NONE

checkpoint_id: CP-001
last_valid_experiment: EXP-003
current_hypothesis: The local Docker Desktop amd64 build will close all pinned ROS and model dependencies
working_tree_status: Existing user Docker-training and guide changes preserved; inference launch, tests, image, script, lock, and this ledger are additional dirty paths
owned_processes: Local Docker build session 59807 for image so101-yolo11n-seg-inference:verification-platform-split
preserved_processes: ai-station ros2 daemon processes only; no user simulation stack was touched
confirmed_conclusions:
  - Launch RED and GREEN are valid at the source contract layer
  - Build wrapper RED and GREEN are valid
disproven_routes:
  - Remote ai-station build context upload is not authorized
open_risks:
  - Full image build and CUDA runtime smoke are not complete
next_command: poll local Docker build session 59807

checkpoint_id: CP-002
last_valid_experiment: EXP-003
current_hypothesis: The ai-station native amd64 build will close all pinned ROS and model dependencies
working_tree_status: Existing user Docker-training and guide changes preserved; inference launch, tests, image, script, lock, and this ledger are additional dirty paths
owned_processes: NONE; local Docker build exited 130 and no container was started
preserved_processes: ai-station ros2 daemon processes only; no user simulation stack was touched
confirmed_conclusions:
  - Launch platform contract has 54 passing targeted tests
  - Build wrapper RED and GREEN are valid
disproven_routes:
  - Local Docker ROS Jazzy build was abandoned at user request in EXP-004
open_risks:
  - Remote image build and CUDA runtime smoke are not complete
next_command: DOCKER_HOST=ssh://ai-station scripts/yolo-seg-inference-container.sh build --image so101-yolo11n-seg-inference:verification-platform-split

checkpoint_id: CP-003
last_valid_experiment: EXP-008
current_hypothesis: NONE; the requested platform split is implemented and its Linux image/runtime boundary is verified
working_tree_status: Existing user Docker-training and guide changes preserved; inference launch, tests, image, script, lock, and this ledger remain uncommitted
owned_processes: NONE; no local or remote task-owned container remains running
preserved_processes: ai-station ros2 daemon processes only; no user simulation stack was touched
confirmed_conclusions:
  - macOS auto selects the host rgbd_object_pose path and MPS
  - Linux auto selects launch-owned Docker execution and CUDA
  - ai-station stable and verification tags both resolve to image sha256:26f32411b4291915d13cd298efdb9f50641b70d7eb6607566ce5e5fcc2e2efae
  - ai-station CUDA smoke passed on NVIDIA GeForce RTX 5080
  - Task-scoped regression suite has 57 passing tests and all static checks pass
disproven_routes:
  - Docker Desktop on macOS is not used for ROS Jazzy or MPS inference
  - Direct Docker Hub access from ai-station is unavailable; the same pinned base manifest is consumed through DaoCloud
open_risks:
  - Four unrelated full-suite tests remain unverified in this worktree because third_party/mujoco_ros2_control is not initialized
  - No live RGB-D ROS graph or physical pick-place acceptance run was requested or performed
retained_runs:
  - /tmp/so101-debug-yolo-docker-inference-20260901
archived_runs: NONE
deletion_candidates: NONE
next_command: NONE
