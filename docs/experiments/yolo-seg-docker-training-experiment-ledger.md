# YOLO11n-Seg Docker Training Task Ledger

```yaml
task_id: so101-yolo-seg-docker-training-20260901
goal: Replace host-venv YOLO11n-Seg fine-tuning with a repeatable Linux NVIDIA Docker image and runner.
success_contract: The repository builds one pinned training image, the host runner mounts immutable inputs read-only and outputs read-write, focused RED/GREEN tests pass, and NVIDIA Docker exposes CUDA on ai-station.
worktree: /Users/matianyi/.codex/worktrees/78474e78-2991-4c4b-9d35-ac0495fbd06b/moveit-demo
branch: DETACHED
base_commit: 9c8a90b87ad60be281199dbeb038c2cdf581de6c
current_commit: 9c8a90b87ad60be281199dbeb038c2cdf581de6c
evidence_root: /tmp/so101-debug-yolo-docker-training-20260901
confirmed_conclusions:
  - The existing training path prepares runtime YAML and then invokes the host yolo CLI.
  - ai-station exposes Docker 29.1.3 and an NVIDIA GeForce RTX 5080 with driver 595.84.
  - Image sha256:3bfb7483fa77c978d452e74dd0f653043b45d88c099c48569761f2c599cae51d exposes torch 2.13.0+cu130, torchvision 0.28.0+cu130, ultralytics 8.4.115, and CUDA on the RTX 5080.
  - Ordinary Python dependencies are installed from the Tsinghua TUNA mirror; the PyTorch cu130 and NVIDIA package sources remain available only for CUDA-specific wheels.
disproven_routes:
  - Treating this request as a one-off container command; the requested deliverable is a reusable Dockerfile.
  - Using the PyTorch cu130 index as the only pip index; ordinary dependencies were downloaded through a slow upstream path.
  - Assuming pip gives the primary index priority over an extra index; ordinary dependencies must be preinstalled from TUNA to keep the extra index CUDA-specific.
open_hypotheses: []
latest_checkpoint: CP-002
next_experiment: NONE
```

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: The Docker training boundary can be specified through executable tests before image implementation.
prediction: Tests fail only because the runner and container entrypoint do not yet exist, then pass after the minimum implementation.
single_variable: Add the repeatable Docker training boundary without changing inference or model-selection behavior.
lifecycle: ISOLATED_STACK
preconditions:
  - Current worktree has no real changes when Git is explicitly bound to this worktree.
  - No SO-101 simulation or YOLO training process is owned by this task.
success_criteria:
  - Focused tests exercise the runner and container entrypoint as processes and pass.
  - Docker image builds from the committed Dockerfile.
  - NVIDIA Docker reports CUDA available during the smoke gate.
failure_criteria:
  - Host Python or venv remains necessary for training.
  - Inputs are mounted read-write, output is not persistent, or GPU access is implicit.
invalid_criteria:
  - Docker daemon, registry, GPU runtime, or checkout provenance is unavailable or polluted.
provenance:
  source_commit: 9c8a90b87ad60be281199dbeb038c2cdf581de6c
  install_overlay: NONE
  runtime_executable: so101-yolo11n-seg-train@sha256:3bfb7483fa77c978d452e74dd0f653043b45d88c099c48569761f2c599cae51d
  ros_domain_id: NONE
  gz_partition: NONE
commands:
  - command: focused RED tests
    exit_code: 1
  - command: focused GREEN tests
    exit_code: 0
  - command: DOCKER_HOST=ssh://ai-station scripts/yolo-seg-training-container.sh build --image so101-yolo11n-seg-train:verification-9c8a90b
    exit_code: 0
  - command: NVIDIA Docker CUDA and locked-version smoke
    exit_code: 0
  - command: container entrypoint --help with --network none
    exit_code: 0
  - command: final focused shell and pytest verification
    exit_code: 0
    result: 10 passed
  - command: two consecutive cached builds with --provenance=false
    exit_code: 0
    result: both exported sha256:3bfb7483fa77c978d452e74dd0f653043b45d88c099c48569761f2c599cae51d
  - command: full so101_demo_py pytest suite from an isolated package mapping
    exit_code: 1
    result: 889 passed and 13 environment/provenance failures
observed:
  - Mac Docker client 29.6.1 is installed but no local server version was returned.
  - ai-station Docker client/server is 29.1.3/29.1.3; GPU is RTX 5080 with driver 595.84.
  - ai-station checkout e6ab8c1 has one unrelated untracked experiment ledger that will be preserved.
  - The first valid RED run failed three tests because the runner and container entrypoint did not exist; the dedicated console-entrypoint RED failed one assertion before setup.py was changed.
  - Docker Hub frontend and base-image pulls timed out; the final image uses the official NVIDIA NGC CUDA 13.0.2 cuDNN runtime image pinned by amd64 digest sha256:4d242f206abc4b9588a6506cce2d88932cc879849395aae3785075179718cc49.
  - Tsinghua TUNA downloaded cuda-bindings at 9.3 MB/s instead of the observed 16 kB/s upstream path; the complete ordinary dependency layer finished in 19 seconds.
  - Default BuildKit provenance attestations changed the top-level manifest-list digest between otherwise cached builds; the runner now uses --provenance=false.
  - Two consecutive final builds exported the same single-image digest sha256:3bfb7483fa77c978d452e74dd0f653043b45d88c099c48569761f2c599cae51d; the image size is 5136066222 bytes.
  - Offline container smoke reported cuda_available=True and device=NVIDIA GeForce RTX 5080.
  - The 13 full-suite failures are outside the Docker training boundary: four require the uninitialized MuJoCo submodule in this worktree, and nine require source-commit provenance unavailable from the isolated /tmp package mapping.
inferred:
  - Static and source-level tests run locally; image build and GPU smoke belong on ai-station.
  - A real epoch was not run because this task changes the reusable environment rather than authorizing a new fine-tuning run; the CLI process boundary, offline entrypoint, CUDA runtime, and mount policy were validated independently.
conclusion: The reusable Docker training boundary meets its success criteria. Inputs are immutable mounts, outputs persist on the host, training runs offline with explicit GPU access, and the image content is identified by digest.
evidence:
  - /tmp/so101-debug-yolo-docker-training-20260901/red-focused-valid.xml
  - /tmp/so101-debug-yolo-docker-training-20260901/red-entrypoint.xml
  - /tmp/so101-debug-yolo-docker-training-20260901/red-tsinghua-index.xml
  - /tmp/so101-debug-yolo-docker-training-20260901/red-provenance.xml
  - /tmp/so101-debug-yolo-docker-training-20260901/green-focused.xml
  - /tmp/so101-debug-yolo-docker-training-20260901/green-entrypoint.xml
  - /tmp/so101-debug-yolo-docker-training-20260901/green-tsinghua-index.xml
  - /tmp/so101-debug-yolo-docker-training-20260901/green-provenance.xml
  - /tmp/so101-debug-yolo-docker-training-20260901/final-focused.xml
  - /tmp/so101-debug-yolo-docker-training-20260901/so101_demo_py-pytest.xml
decision: PASS
next_experiment: NONE
```

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: EXP-001
working_tree_status: only this task ledger after checkpoint creation
owned_processes: NONE
preserved_processes: ai-station unrelated processes and untracked docs/experiments/ai-station-linux-headless-rgbd-four-point-upgrade-experiment-ledger.md
confirmed_conclusions:
  - Existing host-venv training boundary and target NVIDIA Docker capability are observed.
disproven_routes:
  - One-off container command without a maintained Dockerfile.
open_risks:
  - Exact base-image availability and registry access remain to be verified.
next_command: Run focused Docker training tests before implementation.
```

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-001
current_hypothesis: NONE
working_tree_status: task-scoped Dockerfile, runner, entrypoint, tests, guide, package metadata, and ledger changes only
owned_processes: NONE
preserved_processes: ai-station unrelated processes and untracked docs/experiments/ai-station-linux-headless-rgbd-four-point-upgrade-experiment-ledger.md
confirmed_conclusions:
  - Reusable NVIDIA Docker training image built and passed offline CUDA smoke on RTX 5080.
  - Final focused verification passed 10 tests and shell syntax validation.
  - Tsinghua TUNA is the default ordinary Python package index; CUDA-specific wheels keep their official sources.
disproven_routes:
  - Host-venv training as the documented reproducible path.
  - One combined dependency layer that forces CUDA/PyTorch downloads after every requirements.lock change.
open_risks:
  - First build still depends on PyTorch and NVIDIA CUDA package availability and can be slow when those official sources are degraded.
  - Top-level application dependencies and PyTorch transitive dependencies are version-pinned, but wheel hashes and every Ultralytics transitive dependency are not fully locked.
next_command: Use scripts/yolo-seg-training-container.sh train with an approved dataset, base model, and new output directory when a training run is requested.
```
