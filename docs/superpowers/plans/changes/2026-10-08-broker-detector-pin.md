# The broker keeps the image's own YOLO detector; the freeze's package is mounted for everything else

> **Superseded (CP-3467, `2026-10-08-perception-rebaseline-r6-unpin`).** The pin described here is removed; the broker runs the freeze's own detector and rule R6 in the Worker's localizer keeps the cup. This document stays as the record of the deviation while it was in force.

Date: 2026-10-08

Trigger: live L1 (`nonhead-first-episode-c6a995a1-...`) and L2 (`...a4e633bd-...`) on freeze fgNI7yJj, the first runs whose broker executed the freeze's code (`2026-10-08-qualified-role-commands-and-broker-package`). Both ended rc 4 `RESULT_RUN_CONTEXT_INVALID`: `failure_boundary: request_model`, `BROKER_CANDIDATE_AMBIGUOUS`, then `TEACHER_USER_STOP` with `/cup_pose` count 0.

## Cause (OBSERVED, replayed on the saved inputs, same image, same weights, GPU)

`BROKER_CANDIDATE_AMBIGUOUS` is raised by the Worker (`parallel_ros_runtime._candidate_from_response`) when a QUALIFIED reply does not have exactly one candidate. Replaying the broker's YOLO on the saved `rgb.npy` of c6a995a1 and of 147cb073 (`writer-artifacts/p4-replay.out`):

| detector | candidates |
| --- | --- |
| image's baked tree (3624dac7, 2026-09-24) | 1: conf 0.922, bbox [152,188,218,272], 4059 px |
| freeze's tree | 2: conf 0.967 (4257 px) and conf 0.362, bbox [136,215,159,244], 407 px |

Grounded-SAM gives the same single candidate in both trees; the weights and the inputs are the same, so it is neither a mount error nor a different image. Of the 85 files that differ between the two trees, one is in the detector path: `adapters/perception/yolo_seg.py`, `_predict` (`writer-artifacts/p4-yolo_seg.diff`): the baked file calls `predict(source=source)` with the RGB frame; the freeze's calls `predict(source=np.ascontiguousarray(source[:, :, ::-1]))`. That is commit `828af7c91` (2026-09-25, "preserve RGB frame contract at YOLO model boundary"): Ultralytics reads a numpy array as BGR.

## Recorded deviation

The broker keeps the image's detector, deliberately. The known RGB-as-BGR channel bug stays in the broker because CP-3454 and CP-3455, the 17 Teacher PASS runs and the calibrated limits (cup pose, contact limits, the -13.25 mm place offset) were made with it; with the corrected detector the main detection moves (area 4059 to 4257 px, bbox about 1 px, confidence 0.92 to 0.97) and a second 0.36 candidate appears, which the Worker (it requires exactly one) refuses. Changing the candidate-selection rule or the detector is a perception change; this change makes none.

Follow-up and a gate: re-baselining perception with the corrected detector (the second candidate's nature, the shifted masks and every limit that depends on the cup pose) is a follow-up, and it must be closed before any formal collection. Until then the pin stays and its hash is in every run's record.

## Options considered

1. Pin the broker's detector source to the image's baked file, with its provenance recorded. Taken (CP-3394, the coordinator's decision).
2. Accept the corrected detector and add a selection rule. Rejected for now: a perception change that moves every calibrated limit.
3. Revert `828af7c91` everywhere. Rejected: it reintroduces the bug for every consumer, not only the broker.
4. Mount the whole baked `adapters/perception`. Rejected: only `yolo_seg.py` differs, so the narrower mount is the more robust.

## Change

- Durable pin: `$R/deps/broker-detector-baked-3624dac7/` (read-only): `perception/` is a copy of the image's `adapters/perception` (11 files, extracted with `docker create` and `docker cp`, nothing read from `/tmp` at run time) and `manifest.json` (sha256 of every file, the image id, the image's source hash `3624dac7...`, the tree hash `82b8687d...`), with `manifest.json.sha256`. The mounted file is `yolo_seg.py`, sha256 `72d4e1fb3cbd9b0666d28f95bfc440e3756a4005e7b61532625ed1be52e4ce56`.
- `parallel_perception_broker.py`: `PINNED_DETECTOR_SHA256` and `PINNED_IMAGE_SOURCE_SHA256` are fixed in the code; `detector_pin_root()` (`$SO101_BROKER_DETECTOR_PIN_ROOT`, else `<evidence root>/deps/broker-detector-baked-3624dac7` next to the freeze's `experiments/`, else none outside a qualified run); `pinned_detector_source()` verifies the manifest, every file and the fixed hash, refuses a symbolic link, and fails closed with `DETECTOR_PIN_MISSING` (also when a qualified run has no pin) or `DETECTOR_PIN_MISMATCH`; `container_run_argv(detector_pin=)` mounts the file read-only over `<package>/adapters/perception/yolo_seg.py` after the package mount (it requires the package, and checks the hash again) and labels the container `com.so101.detector-sha256=<hash>`.
- `mujoco_parallel_batch._start_broker` passes the pin and writes `<evidence_root>/broker-source-pin.json` (exclusive create; the package root and its source hash, the detector path and hash, the manifest hash, the image source hash) before the process starts. A pin that no longer matches stops the broker before any process.

## Tests

- `test_p3_detector_pin.py` (13): the constants are the baked file's hash and the image's source hash and differ from the freeze's own `yolo_seg.py`; a matching pin returns the file; eight faults fail closed (tampered file, manifest hash, other image, another file changed, manifest or file missing, symbolic link, garbage manifest); the pin root from the environment and from the freeze's evidence root; a qualified run without a pin stops; the mount composition (package first, detector over it, then the image; the label with the hash; `--volume` before the mount); the pin without the package or with a wrong file is refused; no pin, no detector mount; the composition pins and records in a qualified run, records nothing outside one, and stops on a changed pin before any process.
- Replay check (`p4-pinned-replay.zsh`, output `p4-pinned-replay.out`): the pinned broker (freeze package, baked `yolo_seg.py` mounted exactly as `container_run_argv` does) gives exactly one YOLO candidate on the saved inputs of c6a995a1, a4e633bd and 147cb073 (conf 0.922, bbox [152.2,188.0,218.4,272.1], 4059 px: identical to the baked broker).

Rollback: `writer-artifacts/p4-base.tar.gz` (sha256 beside it); delete the new test and the pin directory.

Ledger CP: CP-3460.
