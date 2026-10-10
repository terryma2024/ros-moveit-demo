# SO-101 code-style refactor: latest-only versions, business names, test layout, file splits

Status: design revision 2, 2026-10-10. Owner: root (Claude Opus 5.5). Execution: one Claude Sonnet 5.5 executor at a time. Ledger: CP-3540, CP-3541, CP-3542.

Revision 1 failed independent review, with 14 findings. The reviewer was a fresh Opus instance; AGENTS.md names Astra for this role, and the deviation is recorded. This revision applies every finding together with the user's answers given on 2026-10-10.

## 0. Request and decisions

The user's request, 2026-10-10:
1. Keep only the latest version of versioned code and schemas, with no backward compatibility.
2. Give business names to process-named files and identifiers.
3. Reorganise the tests by module and component.
4. Split oversized files.

User answers, 2026-10-10:
- **U1, workflow.** Keep two profiles: the general runtime workflow, which has recovery, and the Teacher minimal workflow.
- **U2, old data.** The ACT episodes collected so far may become unreadable.
- **U3, adaptive pool and expert validation.** Migrate them from `parallel_batch_v1.yaml` to the current Linux configuration.
- **U4, benchmark.** Split the large benchmark files, and run the explicit `benchmark_test` gate when doing so.

Root decisions (CP-3394):

| # | Decision |
|---|---|
| R1 | **Successive versions** of one thing are deleted except the latest. **Parallel profiles** are kept and renamed by meaning, with no version in the name. Every versioned item is classified first by a mechanical inventory (§1, step 0) into one of: family, profile, single-version rename, allowlist. |
| R2 | Sealed evidence created before this refactor stays on disk as history and becomes unreadable by the new code (U2). This includes the collected ACT episodes, the Head runs and the audits. |
| R3 | Wire and sealed identifiers are renamed without compatibility readers. These are `kind` strings, error codes, env vars and sealed file names. |
| R4 | External callers change in lockstep, but only **active** callers (§5). Sealed handoff trees are frozen history and are not edited (901 files reference old names). |
| R5 | Ledgers and old designs are not rewritten. A rename map (`docs/experiments/so101-code-style-rename-map-20261010.md`) lists every old name with its new name. |
| R6 | Version numbers leave file, module, class, function and constant names. A format that needs a version carries it as a `schema_version` field. |

## 1. Phases (each ends with gates at 0 failures and 0 errors; see §4)

### Step 0: mechanical inventory and the test-path foundation

1. **Mechanical inventory.** Generate the full hit list with the §3 guard regexes (AST-scoped). Classify every hit as family, profile, single-version rename or allowlist, and record it in the rename map as a table. This replaces hand-made lists, so the families listed below are a minimum, not a closed set.
2. **Test path constants.** Add `test/support/paths.py` with `PACKAGE_ROOT` and `REPOSITORY` (demo; teleop gets its own). Rewrite the 249 + 67 `parents[N]` uses, and the `Path(__file__)` data lookups, onto these constants. Content commit.
3. **Test helpers.** Move the helpers to `test/support/` and add `pythonpath` in `setup.cfg`. Delete the `sys.path.insert` lines.
4. **Basename guard.** Turn on the unique-basename guard before any test moves.

### Phase A: shims

- Delete the 14 alias shims (8 in demo, 6 in teleop `unified/task8_*`).
- Delete these aliases: `Task8Runner`, `Task8Error`, `Task8Port`, `Task8LiveError`, `Task8LiveCampaign`, `Task8ReadbackError`, `Task8PhysicalReadback`, `Task8ContactPairs`.
- Delete the console scripts `act_task8_live`, `act_prepare_task8_live`, `act_prepare_task8_live_artifacts` and `act_capture_task6`.
- Migrate the test importers first.

### Phase B: latest-only (one commit per family, each with a collection run and the family's targeted tests)

| Family | Classification | Result |
|---|---|---|
| Workflow: v1/v2 (with RECOVER) and V3 | profiles (U1) | `SO101_WORKFLOW` stays the general runtime workflow, and V3 is renamed `TEACHER_WORKFLOW`. Only v1-only branches, if any, are removed. The Gazebo C++ recovery is untouched. |
| Execution policy v1/v2/v3 | v1 is the general-runtime profile; v2 is a superseded Teacher version; v3 is the Teacher profile | v1 becomes `general_execution_policy.yaml` (schema kept). v3 becomes `teacher_execution_policy.yaml`. v2 and its tests are deleted. |
| Dynamic manifest v1/v2/v3 | v1 is history; v2 is the general profile; v3 is the Teacher profile | v1 readers are deleted. v2 becomes `so101-dynamic-execute` and v3 becomes `so101-teacher-execute`, each with a `schema_version` field. |
| Teacher events V0/V1/V2 | family | V2 is kept as `SO101_TEACHER_EVENT`, and the module is renamed `teacher_collection.py`. |
| ACT result 1/2/3; QC report 2/3 (rule v4); episode seal 1/2; execution snapshot binding 1/2; camera truth 1/2; training config 1/2; dataset 1/2; coordinator journal 1/2; model bundle 1/2/3; runner checkpoint 4/5; HFA-009 v1/v2 | family (U2) | Keep the latest of each and delete the older readers, `allow_legacy` and `_verify_legacy`. Repoint `result_store.py:973` (live commit path) to the latest reader. Delete `engine.py:49` and `episode_qc.py:448`'s v2 pins only if v2 is history; v2 stays as the general-profile manifest. The QC rule label is renamed `act_data_qc`. |
| HeadSimulationPolicy 2/3 | family | Before deleting 2, confirm that the active Head candidate document is schema 3 (finding 14). If no frozen schema-3 document exists, regenerate it as schema 3 first. |
| Measurement contract v1/v2 | family | Keep v2; delete the v1 file and the template branch. |
| Contact policy 2/3/4 | 2 and 3 are a family; 4 is a different kind | Keep 3. Rename 4 to `diagnostic_contact_proposal`. Delete 2. |
| parallel_batch | three axes (finding 3) | (a) **Request contract**: `BatchRequestV2` and `BatchKindV2` are live and are renamed `BatchRequest` and `BatchKind`. `BatchRequestV3`, which is document-only, is merged or deleted. (b) **Execution profiles**: v3 is renamed `linux_cuda`, `v3_act_offline` is renamed `act_offline`, and v5 and v6 are renamed `macos_mps_single_worker_retry` and `macos_mps_single_worker_first_pass`. v4's macOS combination is renamed `macos_mps_two_worker`; its deferred Linux-CUDA combination is deleted, so v4 is macOS only. (c) **History**: the v1 and v2 configs are deleted only after their live uses are replaced — see the next item. |
| parallel_batch v1/v2 live uses | must be replaced first | (1) Inline the frozen constants (`FROZEN_YOLO_WEIGHTS_SHA256`, `FROZEN_GROUNDED_SAM_MANIFEST_SHA256`) into a `parallel_batch/frozen_models.py` read by `parallel_ipc` and `parallel_perception_runtime`. (2) Re-derive the Linux freeze without the v1/v2 field sets. (3) **Resource identity carrier**: `resource_identity.py` hashes the logical path `parallel_batch_v2.yaml` and imports the V2 rule classes. Replace it with an identity built from the `linux_cuda` profile document, and regenerate the receipts it feeds (selection, queue, point drain, teleop full-restart campaign). This is a new identity value; old receipts are history under R2. (4) Repoint the provenance pin in `mujoco_parallel_batch.py:881`. (5) **U3**: point teleop expert validation (`production.py:235`), `run_so101_adaptive_worker_scaling.zsh:58` and `so101-teleop-service.py:132` at `linux_cuda`. Add `ADAPTIVE_POOL` support to the `linux_cuda` profile, and migrate `parallel_adaptive_workers_v1.yaml` to a business name. |
| `parallel_ipc_v4.py` | Darwin IPC profile | Renamed `parallel_ipc_darwin.py`. |
| Single-version names | rename only | `head_search_v2.json` → `head_search_runtime.json`; `teacher_endpoint_v2.yaml` → `teacher_endpoint.yaml` (rule string `teacher_endpoint`); `episode_recorder_v1.yaml`, `moveit_expert_validation_points_v1.yaml`, `top_view_projection_v1.json`, `endpoint_pose_*_v1.yaml` (deleted if only the legacy QC used them), `task8-calibration-*-v1/v2.json` (v1 deleted, the rest renamed in phase D); `parallel_collection_v3.yaml` (schema 1) → `parallel_collection.yaml`; about 64 `*_SCHEMA_V<N>` / `_V<N>` constants; the wire kind `paired_camera_truth_v2_original`. |
| Not versions (allowlist) | — | Model and dataset ids (`yolo11n-seg-v1`, …), vendor STL parts, container and lock ids, `IMAGENET1K_V1`, `sts3215_03a`, `plastic_cup_grounding_dino_augmented_r3.yaml` (a dataset round; renamed in phase C if it can be renamed without retraining). |

### Phase C: business names in code, with test renames and moves (E3/E4 merged here; finding 8)

- **Modules.** The `act/task8_*` modules get names that qualify the calibration they belong to: `pick_place_calibration_*` or `measurement_calibration_*`, plus `pick_place_live_evidence`, `pick_place_validation_artifact_bundle`, `pick_place_phase_camera` and `calibration_production_composition`. `w8_qualification` becomes `parallel_qualification_verifier`. `macos_n1_*`, `macos_w2_*`, `w1_composition`, `w2_composition` and `macos_w2_broker_port` get single-worker and two-worker names. `first_episode` becomes `diagnostic_episode`, `fresh_qc` becomes `independent_qc`, and `candidate_source` becomes `reachability_candidate_source`.
- **Docstrings and identifiers.** "Task N", "CP-#" and "EXP-#" in docstrings become descriptions of what the code does. Class, function and constant names follow their modules.
- **Console scripts.** Renamed, together with `setup.py`.
- **Tests.** In the same commits, tests move into the tree that mirrors `src/` and are renamed by the behaviour they test. The tree absorbs the existing `contracts/`, `characterization/`, `place_height_live/`, `process_summary/` and `native_scene_probe/`. `test_p3_rework` is split by content. Pure `git mv` commits are kept separate from content commits.
- **Teleop.**
  - `test/teleop/*` moves into `test/{expert_validation,unified,pick_place_validation,api}/`.
  - The per-worker IPC conftest is lifted to `test/conftest.py`.
  - `test/e2e` stays a package.
  - The 113 CMake registrations and `test_ctest_registration.py` change in the same commit.
- **Tooling updated in the same phase.** Gate runner duration map to relative paths; host-path guard allowlist keys; `test_explicit_ml_collection` node ids; `scripts/so101-macos-service-campaign-final-gate.zsh` test paths.

### Phase D: business names in wire and sealed identifiers

- **Config files and kinds.** `task8-*` config files become `pick-place-validation-*` or `pick-place-calibration-*`, and their `kind` strings follow (`ACT_TASK8_LIVE` becomes `ACT_PICK_PLACE_VALIDATION`). The `EXP-115` field is dropped.
- **Error codes.** About 193 `TASK8_*`, `TASK6_*` and `TASK1_*` codes get domain prefixes.
- **Env vars.** `SO101_TASK8_*_SEAM` becomes `SO101_PICK_PLACE_CALIBRATION_*_SEAM`, `SO101_TASK12_*` becomes a name for what it does, and `ACT_FIRST_EPISODE_*` becomes `ACT_DIAGNOSTIC_EPISODE_*`.
- **Admission kinds and routes.** `task8_phase`/`task8_full` and the bridge `task8` route are renamed together with the teleop `unified/{bridge,admission,ipc}.py` modules and the web UI.
- **Profile wire values and sealed names.** `ExecutionProfile` values such as `MPS_W2_FIRST_PASS`, the `hs40-{seed}` ids and the sealed `task8-ready-*` names are renamed.
- **macOS profile YAMLs.** Renamed together with `scripts/`, the web fixtures and `.agents`.
- **After the renames.** Digest-bound renames are followed by a fresh freeze and re-activation using the CP-3531 procedure.

### Phase F: split oversized files

- **Scope.** Source files over 1200 lines, about 40 in demo plus 2 in teleop plus 1 C++ file.
- **Order.** Largest first, and bottom-up within the `head_search_*` family.
- **Facades.** A facade exists only while importers are migrated inside the same phase, and is then removed.
- **Benchmark files (U4).** `perception_benchmark/reporting.py` and `runner.py` are split with the `benchmark_test` gate added for that commit.
- **Test files.** Test files over 1500 lines are split by behaviour.
- **Patch targets.** Monkeypatch targets and `module.__file__` text checks change in the same commit.
- **Cycles.** An import-cycle check runs for every split.

## 2. What phase B deliberately does not change

- The general runtime keeps its recovery chain (U1).
- The Gazebo C++ packages are untouched.
- Single-version schemas named `SCHEMA_VERSION = 1` keep their field.

## 3. Guards (AST- and manifest-scoped; finding 10)

- **`test_no_versioned_names`.** Scans file names and module-level `def`/`class`/constant names in `src/` and `test/` of the four packages, plus `console_scripts`. The match is token-bounded on snake_case/CamelCase segments: a whole segment `v\d+` or `V\d+`. Locals and parameters are excluded.
- **`test_no_process_names`.** Same scope. A segment equal to `task\d+`, `t8`, `w\d`, `n1`, `hs\d+`, `cp\d+`, `exp\d+`, `p\d`, `b\d+b?`, `d\d`, `rec\d+b?` or `r\d+b?`, but only when it is a whole segment of a file or module-level name. Geometry identifiers such as `x1`, `q6`, `dq1` and `p1` occur inside functions, so they are not scanned.
- **`test_no_process_wire_strings`.** String literals in `src/` and `config/` matching `TASK\d+_`, `SO101_TASK\d+`, `task\d+[-_]`, or a `"…-v\d+"` kind literal. Phase D makes this pass.
- **Allowlists.** Every allowlist entry carries a reason, and a companion check fails on unused entries.
- **`test_unique_test_basenames`.** Enabled from step 0.
- **`test_no_module_over_lines`.** Fails on any source module over 1200 lines; it starts after phase F, with a reasoned exception list.

## 4. Gates per phase

- **Build.** A fresh build.
- **so101_demo_py ordinary gate.** Run with the grounded-sam interpreter against the install.
- **colcon test.** `colcon test` plus `colcon test-result` for the 10 packages.
- **scripts tests.** `scripts/tests/test_so101_teleop_service.py`.
- **Guards.** The host-path guard and the active guards from §3.
- **Benchmark gate.** Added in any commit that touches `perception_benchmark/` (U4).
- **Ledger.** Root writes a ledger checkpoint after review.

## 5. Active external callers (R4; all others are frozen history)

**In the repo:**
- `scripts/so101-teleop-service.py` and `scripts/tests/test_so101_teleop_service.py`.
- `scripts/so101-macos-service-campaign-final-gate.zsh` and `scripts/so101-macos-service-campaign-live-window.zsh`.
- `scripts/run_so101_adaptive_worker_scaling.zsh`.
- `.agents/skills/so101-dev/references/unified-teleop-service.md`.
- The teleop web e2e fixtures and api tests.
- `setup.py` and the teleop `CMakeLists.txt`.

**In the evidence tree, current versions only:**
- `cycle-r9.zsh`, `live-r14.zsh`, `run-qualified-live-20261010-r17.zsh`.
- `freeze-copy-build-20261010-r10.zsh`, `qualify-copy-build-20261010-r7.zsh`.
- `prepare-qualified-inputs-20261010-r6.zsh`.
- The gate runners in `/tmp/so101-debug-act-data-66c42e4c/` (`run_gate_gsam.zsh`).
- The Head case scripts (`case-v2-001/scripts`).

Each affected caller gets a new version beside the old one, and its sha256 is recorded.

## 6. Live checks

After phases B, D and F:
1. One Head single case, seed 900000, with the CP-3539 criteria.
2. One pick-place Teacher run, with the CP-3539 criteria.
3. One Linux fixed-N parallel batch through the teleop unified service, which is the expert-validation path.
4. One adaptive pool run (U3).
5. An offline dataset smoke: export plus the training-view load of a freshly collected episode.

The macOS v4/v5/v6 routes cannot run on ai-station. They are recorded as deferred, and a static route-table test covers them.

## 7. Risks

- **Size.** Every phase and every phase-B family is its own gated commit, so a bad change can be bisected.
- **The new resource identity value (phase B).** All earlier queue and selection receipts become history.
- **Digest-bound renames (phase D).** They require a new freeze and re-activation.
- **Test moves.** Mitigated by step 0 (path constants, the basename guard) and a full collection after every family.

## 8. Order and stops

Step 0 → A → B → C → D → F, with a root review stop after each. The test reorganisation is folded into step 0 and phase C.
