# SO-101 evidence layout migration ledger

```yaml
task_id: so101-evidence-layout-migration
goal: Consolidate persistent SO-101 evidence below /data/work/so101-evidence without deleting content or changing historical conclusions.
success_contract: Every declared source moves once on the same ext4 filesystem; relative regular-file SHA256, byte size, and count match before and after; no legacy top-level /data/work/so101-debug-* directory or tracked legacy absolute path remains.
worktree: /data/work/ws_moveit/.worktrees/so101-demo-py-canonical
branch: codex/so101-demo-py-canonical
base_commit: d20f12ae465f409f1d88e655367eebb48c57cef2
current_commit: 399fcbf34d34952b80eb9babff10f385315576d5
evidence_root: /tmp/so101-debug-evidence-layout-q2GDCm/
confirmed_conclusions:
  - PRECHECK-001: feature and main worktrees are clean; all 18 sources share device 66309 with /data/work; destination root is absent; no source-path process or open file was found.
  - EVIDENCE-LAYOUT-001: all 18 same-filesystem moves preserve 36,685 regular-file paths, SHA256 values, and 600,949,404 bytes; four latest symlinks were rebased and no broken symlink or legacy top-level directory remains.
disproven_routes:
  - NONE
open_hypotheses:
  - NONE
latest_checkpoint: CP-EVIDENCE-LAYOUT-003
next_experiment: NONE
```

## EVIDENCE-LAYOUT-001

```yaml
experiment_id: EVIDENCE-LAYOUT-001
status: VALID
prior_experiment: NONE
hypothesis: A same-filesystem rename can establish the approved persistent layout without changing any directory content.
prediction: Every destination manifest will exactly match its source baseline and all legacy top-level directories will disappear.
single_variable: Parent path of each declared evidence directory.
lifecycle: FILESYSTEM_MIGRATION
preconditions:
  - Feature HEAD is d20f12ae465f409f1d88e655367eebb48c57cef2 and clean.
  - All declared source directories exist on device 66309.
  - /data/work/so101-evidence does not exist, so no destination conflicts exist.
  - No process command line or open file references a source directory.
success_criteria:
  - Source-to-target mapping is complete and unambiguous.
  - Relative regular-file SHA256, byte size, and file count match before and after for every directory.
  - No /data/work/so101-debug-* entry remains and no tracked legacy absolute path remains.
  - No content is deleted.
failure_criteria:
  - Any manifest, byte-size, count, path-reference, or destination-conflict check differs.
invalid_criteria:
  - A source changes after its baseline manifest or becomes open before its move.
commands:
  - command: Generate mapping and per-source baseline manifests under the unique evidence root.
    exit_code: 0
  - command: Move each source with mv after rechecking its destination, then regenerate and compare manifests.
    exit_code: 0
observed:
  - PRECHECK-001 completed on ai-station without SSH.
  - Baseline v3 covers 18 directories, 36,685 regular files, 600,949,404 regular-file bytes, 285 directories, and 4 symlinks.
  - Mapping SHA256 is 0e45a90c5b2e86a3c17852589447972dff4dd45c0648317d00797a65e8ddec4c; summary SHA256 is f494012422c7232a2730654be19e7fe5d6bb05d49d0898967e4de34c19173800.
  - Post-rebase summary SHA256 is 41f097c66bf0b016b9eed1fd4c43095a4d41ca744678e8feb7b83e3a722030da; all 18 regular-file manifests and directory lists match their baselines.
  - Four moved absolute latest symlinks were rebased to the same relative content; broken symlink count and legacy top-level directory count are both zero.
  - JSON, backend integration, four provenance tests, skill/Markdown structure, historical-content normalization, old-path rg, and git diff checks passed.
  - The first full package verification was environmentally invalid because ROS_LOG_DIR was unset and the sandbox made /home/lenovo/.ros read-only (182 passed, 3 logging-path failures); with ROS_LOG_DIR bound to this task root, the unchanged suite passed 185/185 and backend integration passed.
inferred:
  - NONE
conclusion: The approved retained/archive layout is complete without deleted content or changed historical conclusions.
evidence:
  - /tmp/so101-debug-evidence-layout-q2GDCm/
  - /data/work/so101-evidence/README.md (SHA256 f2041a1c6108d119e7f81d956ca94efdd4c53df8ef9ac00ecdf23249bc13e7b7)
decision: KEEP
next_experiment: NONE
```

## Durable migration map

The immutable pre-move artifact
`/tmp/so101-debug-evidence-layout-q2GDCm/source-to-target.tsv` contains the exact absolute
source-to-target mapping and has SHA256
`0e45a90c5b2e86a3c17852589447972dff4dd45c0648317d00797a65e8ddec4c`.
The source column below is the former `/data/work` top-level basename; this representation avoids
leaving an actionable legacy absolute path in tracked instructions.

| Former top-level basename | Target | Class | Files | Regular bytes | File-manifest SHA256 |
|---|---|---|---:|---:|---|
| `so101-debug-fusion-gazebo-007` | `/data/work/so101-evidence/fusion/so101-debug-fusion-gazebo-007` | retained | 14 | 129757 | `b941ec61798d600a44371a47717533b59e77da52f79c88503b8432651458a36d` |
| `so101-debug-fusion-gui-003` | `/data/work/so101-evidence/fusion/so101-debug-fusion-gui-003` | retained | 871 | 13967567 | `a6271e4eebccc59bb300065ca6ff531d332d34e71359f8af54b8b9e42d9f657f` |
| `so101-debug-fusion-full-restart-004` | `/data/work/so101-evidence/fusion/so101-debug-fusion-full-restart-004` | retained | 4072 | 64571528 | `a0228a41eedfe0183f5601594a008778cf56c642af6d69e86d4b35405f8797ec` |
| `so101-debug-fusion-reset-world-003` | `/data/work/so101-evidence/fusion/so101-debug-fusion-reset-world-003` | retained | 4063 | 64282764 | `10a15740ae71162e6183f4f50a60c50eb2cef2a0d3b9b41b37ef19b713f54fc6` |
| `so101-debug-mujoco-maintainability-remediation` | `/data/work/so101-evidence/maintainability/so101-debug-mujoco-maintainability-remediation` | retained | 13073 | 225585703 | `2393ba44899237b4de60aac033cf05c4c9c72c32282e8b168312da9fa986a200` |
| `so101-debug-fusion-full-restart-001` | `/data/work/so101-evidence/archived/fusion/so101-debug-fusion-full-restart-001` | archived | 1481 | 23994880 | `7cd6e539fa27ae02a0a508c363cd98d643beadff12bc019baff6554ffe8ff632` |
| `so101-debug-fusion-full-restart-002` | `/data/work/so101-evidence/archived/fusion/so101-debug-fusion-full-restart-002` | archived | 4140 | 65669286 | `9a754a94e2047f9896de252d818560a9eb9b172bf2917ad886ab4969ddeb296d` |
| `so101-debug-fusion-gui-001` | `/data/work/so101-evidence/archived/fusion/so101-debug-fusion-gui-001` | archived | 852 | 13697655 | `ac9b130132b9e4a9f5a9af5dc93d61145b944dc6ef2f3a6e4c79d91d735e7c0e` |
| `so101-debug-fusion-reset-world-001` | `/data/work/so101-evidence/archived/fusion/so101-debug-fusion-reset-world-001` | archived | 4193 | 66074717 | `acba8743884a8ee29fc749c4b6ed5b63d0636e7c0970646a146db329f6f2b2a6` |
| `so101-debug-fusion-smoke-001` | `/data/work/so101-evidence/archived/fusion/so101-debug-fusion-smoke-001` | archived | 3 | 34079 | `f56bca51e032e4031e23ee248dcffa72f10dce71603cb28abc8a7d0540109b49` |
| `so101-debug-fusion-smoke-002` | `/data/work/so101-evidence/archived/fusion/so101-debug-fusion-smoke-002` | archived | 3 | 31295 | `e478091bffd3ee58fcf55b0598b515ed6d7352219867ea5b69b1a59befd49e3c` |
| `so101-debug-fusion-smoke-003` | `/data/work/so101-evidence/archived/fusion/so101-debug-fusion-smoke-003` | archived | 3 | 38163 | `f75b739711685e6c6d7d72005abc28ebfd555fe26cf5b008737959b667d1fd5b` |
| `so101-debug-fusion-smoke-004` | `/data/work/so101-evidence/archived/fusion/so101-debug-fusion-smoke-004` | archived | 765 | 12354796 | `98ea475fa44d6992169499937ec4404d3d1ed44eaf360c5e80d37682d1ba2db2` |
| `so101-debug-fusion-smoke-005` | `/data/work/so101-evidence/archived/fusion/so101-debug-fusion-smoke-005` | archived | 772 | 12456044 | `d312f76979e263dd87ad034d1e9117a0f4b770474da1de6d1ec5cc881a7e5993` |
| `so101-debug-fusion-smoke-006` | `/data/work/so101-evidence/archived/fusion/so101-debug-fusion-smoke-006` | archived | 779 | 12529663 | `a1dae311ca945460b9ee79634da83c93717a32abe8f6ce067f8371d86169d6f8` |
| `so101-debug-fusion-smoke-007` | `/data/work/so101-evidence/archived/fusion/so101-debug-fusion-smoke-007` | archived | 5 | 42394 | `aaaf37b17a1f0979215673446d839afbd789f2ce80b3861668ece455e5367b40` |
| `so101-debug-fusion-smoke-008` | `/data/work/so101-evidence/archived/fusion/so101-debug-fusion-smoke-008` | archived | 814 | 12801944 | `67c1988b0fddef1ad051d0cc2beec4b703ac06fc55cb4baa256f13c54dfc8973` |
| `so101-debug-so101-demo-py-fusion-SyIBjl` | `/data/work/so101-evidence/archived/fusion/so101-debug-so101-demo-py-fusion-SyIBjl` | archived | 782 | 12687169 | `03785f0dabae5056349df65f87c401f2304bc00de11d1cd924a412342b12b1cf` |

Totals: 18 migrated roots, 36,685 regular files, and 600,949,404 regular-file bytes.
Four absolute `latest` symlinks were rebased to the same relative content under the new roots;
there are no broken symlinks below `/data/work/so101-evidence`.

## CP-EVIDENCE-LAYOUT-001

```yaml
checkpoint_id: CP-EVIDENCE-LAYOUT-001
last_valid_experiment: NONE
current_hypothesis: EVIDENCE-LAYOUT-001
working_tree_status: docs/experiments/so101-evidence-layout-migration-experiment-ledger.md added by this task; no pre-existing dirty paths
owned_processes: NONE
preserved_processes: Existing MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui tmux sessions; no relevant ROS runtime nodes
confirmed_conclusions:
  - Feature/main provenance, filesystem identity, target absence, and source non-use passed PRECHECK-001.
disproven_routes:
  - NONE
open_risks:
  - Migration has not started; baseline manifests are not yet generated.
next_command: Generate the explicit mapping and per-directory baseline manifests.
```

## CP-EVIDENCE-LAYOUT-002

```yaml
checkpoint_id: CP-EVIDENCE-LAYOUT-002
last_valid_experiment: NONE
current_hypothesis: EVIDENCE-LAYOUT-001
working_tree_status: task ledger added; migration has not started
owned_processes: NONE
preserved_processes: Existing MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui tmux sessions
confirmed_conclusions:
  - Baseline v3 contains 18 complete per-directory relative-path SHA256/size manifests and passed independent cross-checks for the first four directories.
  - All destinations remained absent and no source-path open file or process was present immediately after hashing.
disproven_routes:
  - Per-file subprocess generator produced only a four-directory partial baseline within its command window; retained but excluded.
  - First batch generator ran sha256sum from the wrong CWD and produced unusable hashes; retained as pre-v2 but excluded.
open_risks:
  - Moves and post-move comparisons remain pending.
next_command: Create destination parents and apply each same-device mv from source-to-target.tsv.
```

## CP-EVIDENCE-LAYOUT-003

```yaml
checkpoint_id: CP-EVIDENCE-LAYOUT-003
last_valid_experiment: EVIDENCE-LAYOUT-001
current_hypothesis: NONE
working_tree_status: Task-owned documentation, instructions, path references, and ledger are ready for final commit; no pre-existing user changes were present.
owned_processes: NONE
preserved_processes: Existing MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui tmux sessions remain untouched; ROS graph remains empty.
confirmed_conclusions:
  - Migration and repository policy update commit: 399fcbf34d34952b80eb9babff10f385315576d5.
  - Retained: four fusion qualification roots and one maintainability root.
  - Archived: thirteen superseded fusion roots.
  - Deletion candidates: NONE identified or authorized; no content was deleted.
  - Relative regular-file manifests, sizes, and counts match 18/18; all destination roots are on device 66309.
  - No direct top-level /data/work legacy evidence directory, broken migrated symlink, or tracked concrete legacy absolute path remains.
  - Historical ledgers/provenance normalize byte-for-byte to their pre-change contents after path substitution, so conclusions are unchanged.
  - Final scoped package verification passed 185/185 after binding ROS_LOG_DIR to the registered task evidence root; the earlier three failures were reproduced and isolated to the read-only default ROS log directory.
disproven_routes:
  - The initial bounded and wrong-CWD manifest generators remain excluded; pre-v3 is the accepted immutable baseline.
open_risks:
  - The migration audit root is in /tmp and is not itself a durable evidence batch; the durable mapping and hashes are preserved in this ledger.
  - Four older historical fusion roots were already absent before this migration; their ledger paths were normalized to the archive namespace without fabricating evidence.
next_command: Run final verification, commit locally, and keep the feature branch/worktree in place without push or merge.
```
