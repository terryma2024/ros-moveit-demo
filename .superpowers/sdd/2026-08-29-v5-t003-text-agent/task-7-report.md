# Task 7 report — local safety boundary documentation and gate

## Documentation

Added a learner-facing `text_pick_agent` section to `src/so101_demo_py/README.md`. It documents
preview, double-authorized execution with shell-resolved live provenance, the sole
`DEEPSEEK_API_KEY` source, one-way local `qwen3.5:4b` Ollama fallback, closed JSON command shape,
V5-T003 rejection of every nonempty constraint, fixed gate order, and the evidence boundary between
preview, state-machine start, runtime completion, and V5-T005 physical proof.

## Local verification

All Task 7 artifacts are retained beneath the sole registered root
`/tmp/so101-debug-v5-t003-text-agent-20260829-164105/`, in the `task7/` artifact subdirectory,
with `ROS_DOMAIN_ID=197` and `GZ_PARTITION=v5-t003-text-agent-task7-local-20260829-164105`.

- Candidate `colcon build --packages-select so101_demo_py --symlink-install`: exit 0.
- Focused six-file suite: **139 passed**, exit 0; JUnit `text-agent-focused.xml` has 0 errors and
  failures.
- Full `so101_demo_py` pytest: **692 passed**, exit 0; its JUnit has 0 errors and failures.
  `colcon test-result --verbose` over the retained Task 7 root reports 831 tests, 0 errors,
  0 failures, 0 skipped because it also discovers prior retained JUnit files.
- `rclpy` resolved to the Jazzy install; source `HEAD` was
  `25c30bec8aae4dd5fc0ca6b29945febe660f9d87`; the installed prefix was
  `/Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/v5-t003-text-agent/install/so101_demo_py`,
  with executable `lib/so101_demo_py/text_pick_agent`.
- The installed CLI was called through a locally injected `PlannerCandidate`, not a cloud or live
  model: `local-preview.json` is one `DISPATCH_PREVIEW` JSON document with `dispatch=false`, valid
  `plastic_cup/pick/{}`, capability `dynamic_cup_pick_place`, and
  `provider=ollama`, `model=qwen3.5:4b`, tokens `7/11`, `fallback_used=true`. The contract check
  also confirmed no `DEEPSEEK_API_KEY` appears in the result.

No physical/runtime dispatch, ROS stack, remote contact, or ai-station action was performed.

## Ledger and evidence disposition

`EXP-001` is `VALID` only for local semantic, dispatch-preview, package, and installed-entry-point
gates. `CP-002` preserves original/parent dirty paths found by read-only inspection and makes
ai-station preview plus authorized dispatch `EXP-002`; it expressly does not claim V5-T005 physical
success.

Retained: all Task 7 logs/JUnit and the preserved initial failed ad-hoc preview command under the
registered root. Archived: none. Deletion candidates: none; nothing was deleted.

## Review correction

The registered evidence root is the parent `/tmp/so101-debug-v5-t003-text-agent-20260829-164105/`;
`task7/` and `task7-review-fix/` are retained artifact subdirectories, not separate roots. The
live documentation snapshot was `44a4471cd1df4d6d15e8f69cf1eeea66f295ba2d`; the ledger now uses
`LIVE_GIT_REV_PARSE_HEAD` for future actions rather than claiming a tracked file contains its own
final commit SHA. `EXP-001` continues to name its actual validated implementation commit
`25c30bec8aae4dd5fc0ca6b29945febe660f9d87`.

`task7-review-fix/offline_preview.py` is a retained, injected offline proof. With the installed
candidate overlay it produced exactly one JSON document, exit 0, empty stderr, `DISPATCH_PREVIEW`,
`dispatch=false`, the validated command/capability, and `ollama/qwen3.5:4b` metadata with fallback
and tokens. Its import guard rejects `rclpy` and runtime modules; its socket guard blocks network
use; its `NoDispatch` executor raises if preview tries to dispatch. Invocation evidence records
live HEAD, installed prefix, CLI module path and SHA256. The earlier failed ad-hoc command and the
first script attempt are retained; nothing was deleted.

`RUNTIME_STARTED` means only that executor dispatch was attempted. A state-machine-start claim
needs correlated runtime session/log evidence. `RUNTIME_COMPLETED` remains a runtime return value,
not V5-T005 physical proof. No live provider, runtime dispatch, remote action, or physical claim
was made by this correction.
