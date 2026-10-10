# SO-101 code-style refactor: latest-only versions, business names, test layout, file splits

Status: design, 2026-10-10. Owner: root (Claude Opus 5.5). Execution: one Claude Sonnet 5.5 executor at a time. Ledger: CP-3540, CP-3541.

## 0. User request and decisions

The user asked for four things on 2026-10-10:

1. Keep only the latest version of versioned code and schemas, with no backward compatibility.
2. Rename process-named files and identifiers (task6/task8/r1…) to business names.
3. Reorganise unit tests by module and component.
4. Refactor oversized files for readability.

Root decisions (CP-3394, recommended):

| # | Decision | Reason |
|---|---|---|
| R1 | "Latest-only" applies to **successive versions of the same thing**. Parallel profiles that share a version counter are **not** versions: they are kept and renamed by meaning. The cases are `parallel_batch` v3 (Linux CUDA) and v4/v5/v6 (three macOS MPS routes), contact-policy schema 4 (a diagnostic proposal kind), and the boundary schemas (two kinds). | Deleting them would delete the Linux path or two macOS routes, which the user did not ask for. |
| R2 | Sealed on-disk evidence created before the refactor (p9–p12 episodes, Head runs, CP-3532/3539 audits) becomes unreadable by the new code. It stays on disk unchanged as history, and the ledgers keep citing it. | The user said "无需兼容老版本" (no compatibility with old versions). |
| R3 | Wire and sealed identifiers are renamed: `kind` strings, error-code prefixes, env vars and file names inside sealed bundles. Because R2 already accepts that old evidence breaks, there is no compatibility reader. | One vocabulary; no dual names. |
| R4 | External callers change in lockstep with every rename. These are the zsh wrappers under the evidence tooling, `scripts/`, web e2e fixtures, `.agents` skill docs, `setup.py` console scripts and the teleop CMake ctest registrations. New tooling versions go beside the old ones. | Renames must not break tooling silently. |
| R5 | Historical ledgers and design docs are not rewritten. A rename map document (`docs/experiments/so101-code-style-rename-map-20261010.md`) maps every old name to its new name. | Evidence stays citable. |
| R6 | Version numbers stay inside documents as `schema_version` fields where a format needs one, but they leave file, module, class and function names. For example, `teacher_execution_policy_v3.yaml` becomes `teacher_execution_policy.yaml` with `schema_version: 3`, and `ParallelRuntimeConfigV3` becomes `LinuxCudaRuntimeConfig`. | Names express meaning; the format carries its version. |

## 1. Phase plan

Every phase ends with:

- a fresh build;
- the full gates at 0 failures and 0 errors: `so101_demo_py` with the grounded-sam interpreter against the install, and colcon test + test-result for the 10 packages;
- the host-path guard;
- separate commits for pure `git mv` moves and for content changes;
- a ledger checkpoint by root.

Phases B, D and F also run live checks (§7).

### Phase A: drop the compatibility shims

- Delete the 14 `sys.modules` alias shims and the `Task8Runner`/`Task8Error`/`Task8Port` aliases, after migrating their importers (tests only).
- Delete the retired console scripts `act_task8_live`, `act_prepare_task8_live`, `act_prepare_task8_live_artifacts` and `act_capture_task6`. Their business-named twins already exist.

### Phase B: latest-only versions

For each family the latest member is kept and the older members, plus their reader branches, are deleted:

| Family | Keep | Delete |
|---|---|---|
| Teacher execution policy | v3 (renamed `teacher_execution_policy.yaml`, schema 3) | v1/v2 files, `EXECUTION_SCHEMA_V2`, the v1 defaults in `dynamic_mujoco_execution.py:430` and `dynamic_runtime.py:536,822`, `first_episode_inputs.py:632`, `TEACHER_POLICY_BINDINGS` v1 pair, byte/hash pin tests for v1/v2 |
| Workflow | V3 (renamed `SO101_WORKFLOW`) | v1/v2 workflow, RECOVER_* states, `VALIDATION_FAILED` path, `_V3_FORWARD` relation tests |
| Dynamic execute manifest | v3 (renamed schema id `so101-dynamic-mujoco-execute`, schema 3) | v1/v2 writers, readers and constants (`dynamic_manifest`, `e2e_acceptance`, `episode_qc`, `offline/engine`, `parallel_ros_runtime`), macOS web fixtures using "…execute-v1" |
| Place height | v3 strategy | v1/v2 code paths; v1's numeric offset stays as the v3 fallback field value |
| Teacher events | V2 (renamed `SO101_TEACHER_EVENT`, module `teacher_collection.py`) | V0/V1 constants and reject branches |
| ACT result | schema 3 | schema 1/2 readers, `_verify_legacy`, `allow_legacy` |
| QC report | schema 3 / rule v4 (rule label renamed `act_data_qc`) | schema 2, `legacy=` paths, `recompute_legacy_native_qc_v2`, `endpoint_pose_*` legacy files if only legacy uses them |
| Episode seal | 2 | 1 |
| Execution snapshot binding | 2 | 1 |
| Camera truth | 2 | 1 |
| HFA-009 audit | v2 | v1 native-close branch and its test |
| Training config | 2 | 1 |
| Coordinator journal | 2 | 1 |
| HeadSimulationPolicy | 3 | 2 |
| Measurement contract | v2 | v1 file and template branch |
| Contact policy | 3 and 4 (4 is a different kind: renamed `diagnostic_contact_proposal`) | 2 |
| Runner checkpoint | 5 | 4 migration |
| Perception model bundle | 3 | 1/2 |
| Dataset | 2 | 1 (and `_LEGACY_SPLITS`) |
| parallel_batch | v3 Linux and v4/v5/v6 macOS, renamed by profile (R1) | v1/v2 files, `ParallelRuntimeConfigV2`, `BatchRequestV2`, the v1/v2 carrier bindings in `resource_identity` and `mujoco_parallel_batch:881`, `read_historical_contract` history paths; teleop `production.py:235` and `scripts/run_so101_adaptive_worker_scaling.zsh` repointed |

Model and dataset identifiers (`yolo11n-seg-v1` …), vendor STL part names, container and lock ids, and single-version `SCHEMA_VERSION = 1` constants are not families and are left unchanged.

### Phase C: business names, code only

- `act/task8_*` modules become the business names from the inventory, for example `calibration_measurement_*`, `pick_place_live_evidence`, `pick_place_validation_artifact_bundle`, `pick_place_phase_camera`, `calibration_production_composition`, `parallel_qualification_verifier`. "Calibration" collisions get a `pick_place_` or `measurement_` qualifier.
- The w1/w2/n1 names become `single_worker` and `two_worker`.
- `first_episode` becomes `diagnostic_episode`.
- `fresh_qc` becomes `independent_qc`.
- `candidate_source` becomes `reachability_candidate_source`.
- `teacher_collection_v2` becomes `teacher_collection`.
- The "Task N"/CP references in docstrings and comments become behaviour descriptions.
- Class and function names follow the module names.
- Console scripts are renamed, and `setup.py` is updated with them.
- `prepare_horizon`, `candidate`, `gate`, and `fresh` where it means freshness keep their names.

### Phase D: business names, wire and sealed

- Config files: `task8-*` becomes `pick-place-validation-*` or `calibration-*`. The `kind` strings follow (`ACT_TASK8_LIVE` becomes `ACT_PICK_PLACE_VALIDATION`). The `measurement_experiment: EXP-115` field is dropped.
- About 193 `TASK8_*`/`TASK6_*`/`TASK1_*` error codes become domain prefixes, for example `PICK_PLACE_VALIDATION_*`, `CALIBRATION_*`, `SYNC_CAPTURE_*`.
- Env vars: `SO101_TASK8_*_SEAM` becomes `SO101_CALIBRATION_*_SEAM`, `SO101_TASK12_*` becomes a name describing its function, and `ACT_FIRST_EPISODE_*` becomes `ACT_DIAGNOSTIC_EPISODE_*`.
- The admission operation kinds `task8_phase`/`task8_full` and the bridge `task8` route are renamed, together with the web UI.
- The `hs40-{seed}` case ids and the `task8-ready-*` sealed output names are renamed.
- The macOS profile YAMLs are renamed with `scripts/`, the web fixtures and the `.agents` docs.
- Every digest-bound config rename is followed by a fresh freeze and a re-activation via the CP-3531 procedure.

### Phase E: test reorganisation

1. Add a `test/support/paths.py` module with `PACKAGE_ROOT` and `REPOSITORY`. Rewrite the about 287 + 73 `parents[N]` uses to it (content commit).
2. Move the helpers to `test/support/` (with `pythonpath` in `setup.cfg`) and drop the `sys.path.insert` lines.
3. Move tests family by family into a tree that mirrors `src/`, using pure `git mv` commits: `act/{head_search,head,teacher,collection,training,calibration,pick_place_validation}`, `adapters/…`, `application/`, `backends/`, `cli/`, `control/`, `core/`, `parallel_batch/`, `perception_benchmark/`, `ports/`, `profiling/`, `ros/`, `runtime/`, `training/`, `repo/`, `characterization/`, `fixtures/`.
4. Rename the process-named test files (b1–b4, c, d1–d4, p2/p3, rec*, r11, task8, w2…) by what they test. `test_p3_rework` is split by content.
5. Add a guard test that keeps basenames globally unique.
6. Teleop: move `test/teleop/*` into `test/{expert_validation,unified,pick_place_validation,api}/`, lift the per-worker IPC conftest to `test/conftest.py`, and rewrite the 114 CMake registrations.
7. Fix the gate runner's duration map to use relative paths, re-key the host-path guard allowlist, update `test_explicit_ml_collection` node ids and the zsh final-gate script paths.
8. After each family move: a full collection plus the gate.

### Phase F: split oversized files

- **Threshold:** source files above 1200 lines (about 43), worked largest first and dependency-bottom-up within the `head_search_*` family.
- **Pattern:**
  - A module becomes a package or a set of cohesive modules, with the old module kept as a thin facade only while internal importers are migrated in the same phase.
  - The facade is then removed: no compatibility layer is left (consistent with R2).
  - Big classes are split into collaborators or mixins by responsibility.
  - Splits follow the inventory proposals: `mujoco_parallel_batch` → provenance, rpc_proxies, composition_broker/workers, outcome_documents, cli; `head_search_calibration` → `cli/head_search/<command>.py`; `dynamic_mujoco_execution` → evidence, teacher, safety, planning, motion, release, scene, phases; `contracts` → after phase B only the live profiles remain, split by profile plus common; and so on.
- **Tests:** tests that patch module globals or read `module.__file__` text are updated in the same commit.
- **Large test files:** test files above 1500 lines are split by the behaviour they test, in phase E or F.
- **Cycle check:** `python -X importtime` or an import-graph test proves no new import cycles.

## 2. Guard tests added by this refactor

- `test_no_versioned_names`: no file, module, class or function name ends in `_v<N>`/`V<N>`, except an allowlist of model, dataset, vendor and container ids, each entry with a reason.
- `test_no_process_names`: no `task\d`, `t8`, `r\d+b?`, `p\d_`, `rec\d`, `b\d_`, `d\d_`, `w\d`, `hs40`, `cp_\d`, `exp\d` tokens in file or module names, public identifiers or console scripts, with an allowlisted exception list.
- `test_unique_test_basenames` (phase E).
- `test_no_module_over_lines`: source modules ≤ 1200 lines, starting after phase F; any exception is listed with a reason.

## 3. Out of scope

- `third_party/`.
- Historical docs and ledgers (R5).
- Benchmark logic changes. `benchmark_test/` is reorganised only if its names are process-named.
- The Gazebo packages, except where a rename crosses into them.

## 4. Risks

- **Size.** About 470k lines are touched across 6 phases. Each phase is gated and committed separately so it can be bisected and reverted.
- **Silent breakage of external tooling.** Covered by R4, by new tooling versions, and by the live checks after phases B, D and F.
- **Digest-bound configs.** A rename forces a new freeze and contact re-activation, which is planned in phase D.
- **Test-depth rewrites (`parents[N]`).** A move can fail only at run time, so a full collection and the gate run after every family move.
- **Monkeypatch targets.** Tests patch module globals, so phase F updates those tests together with each split.

## 5. Live checks

- After phase B: one Head single case 900000 and one pick-place Teacher run, because the policy, manifest and workflow are the latest only.
- After phase D: the same pair, because of the renamed kinds and configs, the new freeze and the re-activation.
- After phase F: the same pair.
- Each check uses the CP-3539 acceptance criteria.

## 6. Order of execution and review stops

The executor stops after each phase for root review, in the order A → B → C → D → E → F. The design itself goes to independent review before phase A.
