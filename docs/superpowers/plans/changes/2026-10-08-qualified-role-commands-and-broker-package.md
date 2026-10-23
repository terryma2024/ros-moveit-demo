# Child roles run the qualified install: the broker package mount and PATH-free role commands

Date: 2026-10-08

Trigger: live L1 and L2 on freeze feAWPg9k (`experiments/nonhead-qualified-inputs.R2zRPv6Y/run-wrapper.log`, `.xXeMAT6t`) ended before the Teacher with `SupervisorError: EARLY_EXIT: broker: 1`. The traceback names `/opt/venv/bin/so101_parallel_perception_broker` and `/opt/venv/lib/python3.12/site-packages/so101_demo/parallel_batch/contracts.py`, `ContractError: FROZEN_RUNTIME_VALUE: lease_duration_s`.

## Cause (OBSERVED)

The broker is the image `so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1` (id `sha256:010dca70...`, built 2026-09-24) started by `docker run ... <image-id> <broker flags>` (`parallel_perception_broker.container_run_argv`, the default route; the run's `owned-processes.json` is empty after its cleanup). `/opt/venv` is the image's own virtual environment. Its `so101_demo` (source tree sha256 `3624dac7c70603039f9337f9f5175f9bf8b427656bf4bf09ed6cd490308d84a2`, the image's `so101.parallel.source_sha256` label) is the tree of its build day. Its `load_runtime_config_any_schema` pins `lease_duration_s` = 300 s, and the ACT runtime config of the P3 switch says 1500 s. Reproduced read-only: the image's python on the ACT yaml raises exactly that error; with the freeze's package mounted over it the file loads (1500/1500) and `so101_demo.cli.parallel_perception_broker`, `runtime.parallel_ipc`, `runtime.parallel_perception_runtime` and `parallel_batch.contracts` import.

This is not a PATH lookup on the host (the premise of the request). The other roles were checked too: the worker is `sys.executable -m so101_demo.cli.mujoco_parallel_batch --internal-worker`, the dynamic consumer, the raw recorder and the processor are `sys.executable -m so101_demo...`; only `ros2` (task station) and `docker` (broker container) were bare names.

## B2: which earlier runs had a broker that was not from the freeze (FACT)

All of them. Every live run since the image was reused (CP-2760), including the 17 Teacher PASS runs and the pilot runs 147cb073 and 429dbf50 (their `run.log` carries `broker_image=so101-parallel-perception:...-v1 (reused, per the coordinator's decision CP-2760)`), ran the broker from the baked tree `3624dac7...`. The source trees of the freezes hash to `91131e04...` (lHwgvaIW), `fb23b807...` (feAWPg9k) and `b2ecaadc...` (VbKc889q); none equals the image's. It went unnoticed because the configs those runs used were all accepted by the older parser.

## Options

- A. Give the broker a config copy its baked parser accepts (the original yaml). Rejected: the config is hash-bound to the inputs and the broker spec, and the two sides would run different code anyway.
- B. Rebuild the image. Rejected: the image identity is pinned (`BROKER_IMAGE_ID`), a rebuild is a new provenance and a new approval.
- C. Mount the running (qualified) `so101_demo` package read-only over the baked one. Taken. The image id stays pinned; what runs inside is the code the Worker's client speaks.

## Change

- `parallel_perception_broker.py`: `IMAGE_PACKAGE_PATH`, `qualified_package_root()` (the package of the running interpreter; inside `<freeze>/qualified-install` whenever `SO101_QUALIFIED_FREEZE` is set, else `QUALIFIED_PACKAGE_OUTSIDE_INSTALL`), `container_run_argv(source_package=)` (absolute, real directory, not a symbolic link, has `__init__.py` and `cli/parallel_perception_broker.py`, else `QUALIFIED_PACKAGE_INVALID`; adds `--volume <pkg>:<image path>:ro` and the label `com.so101.source-sha256`). `mujoco_parallel_batch._start_broker` passes it on the default route.
- `runtime/qualified_commands.py`: `resolve_role_command` (see the amendment 4.7). `ProcessSupervisor(qualified_prefix=)` applies it to the broker and worker; `ProductionBatchComposition` passes the prefix from `SO101_QUALIFIED_FREEZE`; the worker command is now `ProductionBatchComposition.worker_command`; the Worker's process group applies it when `SO101_QUALIFIED_FREEZE` is set.

## Tests (`test_p3_role_provenance.py`, 14)

The container mounts the package read-only before the image id and labels its hash; no mount, no change to the argv; five invalid packages refused; `qualified_package_root` inside and outside the install; the composition's default broker route passes the package and stops before any process when it lies outside; every role command (worker, broker host route, broker container route, task station, dynamic consumer, raw recorder, processor) resolves to an absolute executable under a `PATH` whose first entry is a decoy directory with `so101_parallel_perception_broker`, `docker`, `ros2`, `python3`; bare and decoy-path `so101_*` names, a bare `python3`, and unknown tools are refused; a module and a console script outside the install are refused; the supervisor refuses before `Popen` runs.

The L1/L2 failure itself cannot be reproduced without the image; the read-only checks above are the evidence (`writer-artifacts/p3b-image-check.out`).

Rollback: `writer-artifacts/p3b-base.tar.gz` (sha256 beside it); the new files are removable.

Ledger CP: CP-3459.
