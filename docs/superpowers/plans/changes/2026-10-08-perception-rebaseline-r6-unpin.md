# Perception re-baseline: rule R6 in the Worker's localizer, and the detector pin removed

Date: 2026-10-08

Trigger: ledger CP-3467. CP-3460 pinned the broker to the image's baked `yolo_seg.py` because the corrected detector (commit 828af7c91, the RGB frame reaches Ultralytics as BGR) adds a second candidate next to the cup and the Worker required exactly one. That was a recorded deviation and a gate before formal collection. The investigation (`perception-rebaseline-20261008/findings.md`) showed the second candidate is the red landing ring (`target_landing_tolerance_ring`, flat, 0.05-0.055 m radius, conf 0.35-0.36), present in all 125 saved inputs, and that a Worker-side rule removes it with no change to the cup pose.

## What changed

- `runtime/parallel_ros_runtime.py`
  - `_candidates_from_response` replaces `_candidate_from_response`: every candidate of a qualified response is validated and its mask decoded (an empty list is still `BROKER_CANDIDATE_AMBIGUOUS`).
  - `BrokerMaskLocalizer.localize` runs rule **R6**: localize every candidate with the same localizer, camera info, depth and exact TF as before; keep a candidate only if the xy circle fit succeeds (`GEOMETRY_REJECTED` and `DEPTH_INVALID` drop the candidate) and its world points span at least `MINIMUM_CUP_Z_EXTENT_M = 0.05` m in z. Exactly one must survive, and its pose is the localizer's result for its mask, unchanged.
  - More than one survivor: `RuntimeError("BROKER_CANDIDATE_AMBIGUOUS: <n> of <m> candidates are cups")`. None: `LocalizationError("GEOMETRY_REJECTED", "no candidate is a cup (0 of <m>): <id:reason, ...>")`, which the policy already treats as a normal rejection (it then tries Grounded DINO). A lone candidate that fails keeps its own error, as before. A failure of the shared inputs (`TF_UNAVAILABLE`, `RGBD_INVALID`) is no verdict on a candidate and propagates.
  - `quality_gate` no longer needs a single candidate: a survivor has pixels by construction.
- `cli/parallel_perception_broker.py`: removed `PINNED_DETECTOR_SHA256`, `PINNED_IMAGE_SOURCE_SHA256`, `IMAGE_DETECTOR_PATH`, `DETECTOR_PIN_NAME`, `detector_pin_root`, `pinned_detector_source`, `detector_pin_record` and the `detector_pin` argument of `container_run_argv` (no `yolo_seg.py` mount, no `com.so101.detector-sha256` label). Kept: the freeze-package mount and the `com.so101.source-sha256` label. New `broker_source_record(package)`.
- `cli/mujoco_parallel_batch.py`: in a qualified run (`SO101_QUALIFIED_FREEZE` set) the composition writes `<evidence_root>/broker-source-pin.json` (same name, kind `ACT_BROKER_SOURCE_PIN`, schema 2): package root and source hash, and now the freeze's own detector (`detector_path` inside the package, `detector_sha256`, `detector_source: "freeze"`). The old `manifest_sha256` and `image_source_sha256` fields are gone.
- `$R/deps/broker-detector-baked-3624dac7/` stays as evidence; nothing reads it.
- Grounded DINO query (`runtime/parallel_perception_runtime.py`, `cli/parallel_perception_broker.py`): see below.
- Benchmark (`benchmark_test/`, `perception_benchmark/adapters/yolo.py`): the YOLO adapters now hand Ultralytics BGR (`frame.rgb8[:, :, ::-1]`), as the production detector does; their tests assert it. New gate `test_act_scene_perception_gate.py` with `act_scene_runner.py`.

## Deviation from CP-3462 closed

CP-3460 / CP-3462 recorded that the broker ran the baked detector with the known RGB-as-BGR bug, deliberately, because the earlier evidence and the calibrated limits were made with it. The deviation is closed: the broker runs the freeze's own corrected detector, and the cup pose it produces does not differ from the one the findings measured (below). The old measurement is not repeated; what is new is that exactly one cup survives by construction and the survivor's pose is gated.

## Evidence

Rendered-ACT-scene gate (343 cases: 3 anchors, 300 random positions in x [-0.15, 0.15], y [-0.42, -0.20], 40 positions within 0.12 m of the ring; production image `so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1`, weights `f281d252...`, conf 0.25, NMS 0.7; the production Broker wire conversion and `BrokerMaskLocalizer`):

| | no R6 (CP-3462 code path) | R6 |
| --- | --- | --- |
| exactly one | 274 of 343 (79.9%), 69 `AMBIGUOUS` | **343 of 343** |
| wrong object (xy error > 20 mm) | 0 | **0** |
| xy error mean / p95 / max | | 0.555 / 0.838 / 4.81 mm |
| raw YOLO candidates 1 / 2 / 3 | | 274 / 67 / 2 |
| strata | | anchors 3/3, random 300/300, ring 40/40 |

Gates: exactly-one >= 99%, 0 wrong object, p95 < 1.5 mm. The gate passes in a fresh scratch install through the explicit command `colcon test --packages-select so101_demo_py --pytest-args benchmark_test` (report `writer-artifacts/phased/act-scene-gate-colcon.json`, 18 s for the gate). That command returns rc 1 on this host because of 62 other failures in the benchmark suite (60 in `test_perception_benchmark_dataset.py`, `DatasetVerificationError: RASTERIZE...`; 2 in `test_perception_benchmark_adapters.py`: no `torch` in the test environment, and a synchronizer set-up error). They fail identically with the CP-3471 code (62 failed, 95 passed on the adapters and dataset files), so they are not caused by this change; they are not fixed here. The ordinary gate (`test/`, `-n 8`) does not collect `benchmark_test/`. The numbers equal the findings' R6 row (343/343, mean 0.56, p95 0.84, max 4.81 mm).

Offline check on the 125 saved broker inputs (`writer-artifacts/phased/saved_check.py`, depth re-rendered at the default anchor as in the findings): the corrected detector returns 2 candidates on every one, R6 leaves exactly one on all 125, and the survivor's xy equals the findings' corrected-detector pose to 0.0 mm (largest distance from the default-anchor ground truth 0.474 mm). Output `saved_check.json`, `saved_check-compare.txt`.

## Grounded DINO default query

`Snapshot.query_class_id` defaults to `plastic_cup`, and the Broker sent that to every model. Grounded DINO + SAM declares its prompt profile as `cup` (`manifest.json`: `{"cup": "cup."}`, `target_class_id == "cup"`): asked for `plastic_cup` it raises `UNSUPPORTED_DETECTION_QUERY` (a `ModelRuntimeInfrastructureError`, confirmed in the production image), which the Broker records as an infrastructure failure and marks itself unhealthy. **Reachable in production**: the Worker's snapshot never sets the class (`mujoco_parallel_batch.py`, `macos_w2_broker_port.py`), and the policy falls back to Grounded after any YOLO rejection (a normal rejection, or, with R6, a `GEOMETRY_REJECTED` of every candidate). It never fired in the pilots because YOLO always found the cup. Fixed: `query_class_for(detector, default)` asks a detector for its own `target_class_id` when it has one (the pattern `rgbd_object_pose_node.py` already used), otherwise for the snapshot's class; used in `infer` and in the broker's `--smoke-input` smoke. With `cup` the production image returns one Grounded candidate (0.83) on the default-anchor render. The candidate's `class_id` is then `cup` for Grounded results; nothing downstream reads it.

## Benchmark notes

- The benchmark YOLO adapters (`perception_benchmark/adapters/yolo.py`) fed RGB unchanged to Ultralytics while production feeds BGR; both paths now reverse the channels. Earlier benchmark numbers for YOLO were measured with the unreversed input.
- Weights/README name mismatch (not changed, hash-bound): the registered model id `plastic-cup-yolo11s-seg-v2` (`perception_benchmark/contracts.py`, `benchmark.yaml`) and the production id `plastic-cup-yolo11n-seg-v1` name different sizes, while the README and the HF repo call the weights `yolo11n-seg`, sha256 `f281d252...`. One file, three names; the architecture in the file was not re-derived here.
- 1 px mask-sensitivity from the findings plan is not part of the gate (the findings measured it: <= 0.09 mm at the anchors, p95 <= 0.97 mm over random positions).
- The gate skips with the missing piece named (docker, the model files, the production image) where the ai-station stack is absent, so it cannot go green on macOS by accident. It renders with MuJoCo EGL and runs the container with `--gpus all --network none --read-only`, the package under test mounted over the image's.

## Open risks (not closed by this change)

1. **Start-end distance margin at the left anchor.** `teacher_endpoint.py:179-181` requires a start-end distance > 0.030 m; the left anchor has 3.2 mm margin. A pose bias or a ring-overlap error of that size can flip it. The 0.47 mm common bias would use 15% of it.
2. **Ring-overlap pose errors against the MoveIt tolerance.** The largest errors (2-4.8 mm, about 5% of random positions) occur where the cup overlaps the ring. MoveIt's position tolerance is 0.002 m. The gate's p95 is 0.84 mm but its max is 4.81 mm; a Teacher plan from such a pose may be refused by MoveIt or land short.
3. **Circle-fit bias against the calibration domain.** The fit gives a common ~0.47 mm bias unrelated to the BGR fix. The r10b calibration used the ground-truth start (`contact_collector.py:153-160`), not the perceived pose, and its `left_only` control is a 1 mm y offset: the perceived-pose domain was never calibrated.
4. The gate measures a simulator (rendered depth is exact, no sensor noise); it bounds the pipeline, not the camera.
5. R6's 0.05 m z-extent was chosen from the rendered scene (cup 0.09 m, ring a few mm). A real cup mask that loses its rim or base to depth dropouts could fall under it and be rejected as `GEOMETRY_REJECTED`, which sends the attempt to Grounded DINO (now reachable).

## Tests (RED first)

- `test_parallel_ros_runtime.py`: 8 new R6 tests (RED against HEAD: 7 failed): keeps the cup over a flat ring, drops a candidate whose circle fit is rejected (`GEOMETRY_REJECTED`, `DEPTH_INVALID`), two cups are ambiguous with the count in the message, none is `GEOMETRY_REJECTED`, a lone flat candidate is not a cup and a lone failure keeps its error, shared-input failures propagate, the survivor's pose is the localizer's result, an empty candidate list is ambiguous. The existing mask/TF test returns a localized object with points.
- `test_p3_detector_source.py` (replaces `test_p3_detector_pin.py`): the pin machinery is gone, the argv mounts only the package and labels its source hash, the source record names the freeze's detector, the detector has the BGR reversal, the composition records only in a qualified run.
- `test_parallel_perception_runtime.py`: each model is asked for the class its own prompt profile declares, in `infer` and in the smoke.
- `benchmark_test/test_perception_benchmark_adapters.py`: two assertions now expect BGR, on a frame whose channels differ (the old all-zero frame could not tell the orders apart; RED against CP-3471: 2 failures).
- `benchmark_test/test_act_scene_perception_gate.py`: the gate (explicit) and two Docker-free tests (the summary arithmetic, the camera chain equals the scene camera). RED: without R6 the gate fails with 274 of 343.

## Rollback

`writer-artifacts/p5e-base.tar.gz` (sha256 beside it) holds the files this change and C5 touched as of CP-3471 (HEAD c26df9c5e); `p5e-freeze-list.txt` lists them with their sha256. The pin directory under `$R/deps` was not touched.
