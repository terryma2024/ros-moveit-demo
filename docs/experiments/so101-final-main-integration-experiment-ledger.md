# SO-101 final main integration ledger

```yaml
task_id: so101-final-main-integration
goal: Fast-forward the verified canonical SO-101 feature to main and publish origin/main without changing the qualified runtime contract.
success_contract: Feature and main gates pass at one final clean commit; main advances only by ff-only; non-force push succeeds; remote read-back equals local main and the feature tip.
worktree: /data/work/ws_moveit/.worktrees/so101-demo-py-canonical
branch: codex/so101-demo-py-canonical
initial_feature_commit: fc007ef09ca54f6b531728f5a6c9d8941726ef06
expected_main_commit: 072541a0e537080c3f2abf3945a156b26d06f48d
evidence_root: /tmp/so101-debug-final-main-integration-TbEo1J
status: PLANNED
latest_checkpoint: CP-FINAL-MAIN-001
```

## CP-FINAL-MAIN-001 — preregistered release gates

```yaml
checkpoint_id: CP-FINAL-MAIN-001
recorded_at: 2026-08-13T15:18:28+08:00
status: PLANNED
host: AI-STATION-001
ssh_to_self: false
feature_precheck:
  commit: fc007ef09ca54f6b531728f5a6c9d8941726ef06
  status: CLEAN
  direct_descendant_of_main: true
  commits_ahead: 42
main_precheck:
  local_commit: 072541a0e537080c3f2abf3945a156b26d06f48d
  origin_commit_after_fresh_fetch: 072541a0e537080c3f2abf3945a156b26d06f48d
  status: CLEAN
submodule_gitlink: 738e304551b4ea6db020b466086a13db71b65607
frozen_qualification:
  source_commit: 213ac0da3b4f2a756c2c4e66e8e6c28af9e2168a
  installed_prefix: /tmp/so101-debug-gazebo-python-capabilities-boWK6J/final-candidate-005-install/so101_demo_py
  bundle_sha256: 438f968141ff3b3999799b8dc06d36c386950eed335a82e314a2fe2e050119dd
  policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
  experiment_ids: [cp-gzpy-fr-021-01, cp-gzpy-fr-022-01, cp-gzpy-fr-023-01, cp-gzpy-fr-024-01, cp-gzpy-fr-025-01]
materiality_audit:
  range: 213ac0da3b4f2a756c2c4e66e8e6c28af9e2168a..fc007ef09ca54f6b531728f5a6c9d8941726ef06
  runtime_code_changed: false
  policy_or_assets_changed: false
  dependency_lock_or_installer_changed: false
  changes: Documentation, provenance records, agent evidence policy, and evidence-path migration only.
dependency_lock_assessment:
  path: src/so101_demo_py/config/mujoco/dependency-lock.yaml
  present_at_qualified_source: true
  lock_bytes_changed_after_qualification: false
  locked_gitlink: 738e304551b4ea6db020b466086a13db71b65607
  decision: NOT_A_RELEASE_BLOCKER
  rationale: The installer resolves the canonical package-owned lock that already existed at the qualified source. The lock remains immutable; no hash is fabricated or updated. The historical qualified controller overlay remains untouched. A separately rebuilt top-level fork workspace has path-dependent raw ELF bytes, so it is accepted only through the separately recorded matching interface/header hashes, ABI exports, normalized dynamic contract, and 133-test result; it does not replace the qualified overlay or qualification bundle.
preserved_runtime_state:
  tmux_sessions: [MNT-Q-RESET-EXP136-140, codex, codex-cua, so101-mujoco-gui]
  observed_existing_processes:
    - old_so101_teleop_pytest: [3329300, 3329315, 3329317, 3329322, 3329326, 3329327]
    - old_tf_echo: [3418770, 3418842]
  action: RECORD_ONLY_DO_NOT_CONTROL
release_gates:
  - fresh feature 185-test suite with task ROS_LOG_DIR
  - backend integration contract
  - JSON and provenance tests
  - git diff/check and ancestry
  - removed legacy package directory and active dependency scan
  - installer static and contract checks
  - frozen policy and qualification bundle read-back
  - evidence layout checks
  - top rebuilt fork 133-test and normalized ABI/dynamic-contract status
  - ff-only merge followed by critical complete verification on main
  - non-force push followed by fresh fetch and exact remote read-back
failure_rule: Any failed gate stops before push; qualification material drift stops before merge.
next_command: Commit this integration checkpoint independently, then execute every feature gate at the resulting clean feature tip.
```
