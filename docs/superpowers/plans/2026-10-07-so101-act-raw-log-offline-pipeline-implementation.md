# SO-101 ACT: Raw-Log Recording + Offline Episode Processing — Implementation Plan (handoff to Codex)

- Date: 2026-10-07
- Status: authoritative execution plan for the Codex executor. It supersedes live-Recorder rounds 13+ (ledger CP-3427, CP-3428).
- Author: Claude main agent (Opus 5.5). Executor: local Codex CLI, model `gpt-6.1-sol`, reasoning `high`, YOLO mode, in tmux session `codex-act-offline`.
- Goal: complete ACT training data collection. The concrete milestone is base-plan §5 L2 plus L3–L7.

The L2 milestone means:
- one real MuJoCo pick-and-place in which the Teacher passes and the endpoint check passes;
- complete, lossless, sealed episode data;
- a fresh-process QC PASS;
- a real commit and readback;
- export refused for diagnostic use.

## 0. Authorizations and standing rules from the user

These quote or paraphrase the user and are binding:

- **Decisions:** at every technical decision point that changes the plan, take the recommended option and keep going (CP-3394). For each such decision, write a separate change document under `docs/superpowers/plans/changes/` (format in §9). Also add a ledger entry.
- **Disk cleanup:** you may clean up `/data/work/so101-evidence` to recover disk space (user, 2026-10-07; also CP memory "rm under /data/work pre-authorized"). Constraints:
  - Never delete the evidence of the runs this plan creates.
  - Never delete the current calibration (`<root>/calibration/r10b-20261007T034028Z/`).
  - Never delete the current activated inputs.
  - Never delete the newest successful-Teacher run roots listed in §1.
  - Log every deletion in a TSV: `<root>/deletions-<date>.tsv`, with columns path, size, reason.
  - Report what you deleted in the ledger.
- **Prohibited:**
  - No push, merge, PR, branch, reset, checkout or stash of others' work.
  - No `gh` CLI.
  - No hardware.
  - Never run `ament_uncrustify --reformat`.
  - Do not run the benchmark suite.
  - Do not relax any genuine safety protection: the Teacher's force/compression/collision/hazard/support/deadline/stop checks and the activated contact limits.
- **The Teacher stays untouched** unless a change document justifies it. The data side must never block, delay or cancel the Teacher after it has started. Only its start time may be gated, with a bounded wait; the Teacher always runs.
- Follow `AGENTS.md`:
  - zsh rules;
  - `set -o pipefail`;
  - check `test -x` before long runs;
  - for pytest on ai-station, set TMPDIR/TMP/TEMP to a fresh scratch dir under the evidence root;
  - the `$so101-dev` skill at `.agents/skills/so101-dev/SKILL.md`. Read it first and follow its gates.
- **Ledger:** you are now the ONLY ledger writer (`docs/experiments/so101-act-data-experiment-ledger.md`). Insert new `## CP-34xx` entries before the previous top entry, and update the `latest_checkpoint:` / `next_experiment:` header lines. The last CP written by Claude is CP-3428 or later; check the file.

## 1. Where things are

- **Worktree:** `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a`, branch `codex/so101-act-data-0917a`. There are many uncommitted paths; do NOT reset or clean, and do not commit unless a step says so.
- **Evidence root** `R=/data/work/so101-evidence/act-data/20260924-fbc25063-resume`:
  - experiments: `$R/experiments/`
  - scratch: `$R/scratch/`
  - test venv python: `$R/test-venv/bin/python`
- **Tooling** `TD=$R/handoffs/teacher-act-decoupling-20261005.1RmsJ3ZJ/tooling`:
  - `cycle-r4.zsh <tag> <proposal.json> <receipt.json> [source_root] [gates]` does freeze, gates (demo, support, teleop), inspect, the contact-role helper and prepare, then prints F/I/P. Use the NORMAL activation receipt (below) for both the proposal and the receipt arguments' receipt.
  - `live-r3.zsh <P> <F> on|off <fault>` does prestart and run, with the watcher, on `ROS_DOMAIN_ID` 181. An inputs dir P is single-use; prepare a new one per run with `$R/handoffs/codex-nonhead-takeover.zya51rHz/prepare-qualified-inputs-20261006-r4.zsh <F> <helper-dir-name>`.
  - Old revisions are kept. Create new tool revisions as new files; never edit old ones.
- **Contact calibration (active):**
  - proposal `$R/calibration/r10b-20261007T034028Z/proposal.json`, fingerprint `131c2bdc…`;
  - normal activation receipt `$R/calibration/r10b-20261007T034028Z/activation-receipt.json`.
- **Latest freeze:** `nonhead-installed-freeze.TY1CPObX` (round 12b). Its last live L2 run is `nonhead-first-episode-6062afd8-…`: Teacher PASS, data INVALID.
- **Retained successful-Teacher runs (keep):** `nonhead-first-episode-c2a9e148…` (D5a), `…2fb60257…` (D5b), `…8f834bb0…` (L1 PASS), and `…81fa2857…` (378 rows).
- **Writer artifacts and history:** `$R/handoffs/teacher-act-decoupling-20261005.1RmsJ3ZJ/writer-artifacts/`. These hold the `rec*-analysis.md` files, `rec11-consistency.md`, `rec9-start-sequence.md` and `rec12-pacing.md`. The draft this plan builds on is `offline-pipeline/2026-10-07-offline-record-then-process-draft.md`. Read them.
- **Design chain:**
  - `docs/superpowers/specs/2026-10-05-so101-teacher-act-decoupling-amendment.md`
  - `docs/superpowers/specs/2026-10-06-so101-teacher-moveit-simplification-amendment.md`
  - plan `docs/superpowers/plans/2026-10-06-so101-teacher-moveit-simplification-implementation.md`, sections R0–R10 plus dated amendments
  - ledger CP-3363…CP-3428

## 2. Why this change

- **The Teacher works.** It has 12 consecutive live PASSes on the MoveIt/JTC path, with the official-aligned model, the recalibrated cup limits and the −13.25 mm place offset.
- **The live Recorder does not.** Every live L2 failed on the data side: start races against the Teacher's first command, delivery deadlines, GIL/GC stalls, alignment sources not yet arrived, and cascades from one latched failure. Each fix round surfaced the next live-only defect.
- **The user's decision (CP-3428):** record raw data during execution in a record-only process, then build the episode offline from the recorded log. Pilot first; switch once a VALID, QC-PASS episode is produced.

## 3. Target architecture

1. **Record-only process (live).**
   - Use `ros2 bag record -s mcap`. `rosbag2_storage_mcap` is verified installed on Jazzy.
   - Start it from the worker/orchestrator AFTER the worker reset and BEFORE the Teacher. Run it as its own process group, outside the Teacher.
   - Record every topic the episode needs. Enumerate them from the current Recorder code (`ros/episode_recorder_sources.py`, the `act/chunk_spool.py` and `act/controller_spool.py` topics, the camera topics and the event topic):
     - head and wrist images and camera_info;
     - the physics evidence chunk topic;
     - `/so101/simulation/evidence`;
     - the robot contact topic;
     - the scene-state topic;
     - `/joint_states`;
     - `/arm_controller/controller_state`, `/gripper_controller/controller_state` and `/neck_controller/controller_state`;
     - `/so101/teacher/events`;
     - `/clock`.
   - QoS overrides (`--qos-profile-overrides-path`) match each publisher. Use reliable where the publisher is reliable, and a deep history.
   - **Planning scene.** The Teacher's `scene_operation` events already carry the request/response CDR. Also add a record-only scene poller node: it calls `/get_planning_scene` at about 20 Hz and publishes each response with request and response stamps to a recorded topic. The live Recorder's poller can be reused as a library.
     - Use `--services` (service introspection) only if move_group can enable it without code changes. Verify that.
   - **"RECORDING" readiness:** the orchestrator waits, bounded, with a frozen timeout, until the bag has received ≥1 message on every required topic. Determine this from `ros2 bag record` logs or a tiny readiness subscriber. Then it starts the Teacher. On timeout the Teacher starts anyway and the data is INVALID.
   - At the end, the bag stops after the Teacher's `terminal` event plus the endpoint settle tail. Close it cleanly, run the `ros2 bag info` readback, and record per-topic counts.
2. **Offline processor (after the run, pure Python).**
   - Place it in a new package dir `src/so101_demo_py/src/act/offline/`.
   - It reads the MCAP with `rosbag2_py` or the `mcap` Python reader, ordered by producer time. Feed the EXISTING modules (synchronizer `source_age_ok_ns`, source alignment, collection_reference labels, episode_assembly, `EpisodeRecorder`/lossless writer, seal, `episode_qc`) through a source interface instead of live callbacks.
   - It produces the sealed episode in `<attempt>/sealed/episode/`, in the same layout that QC, ResultStore and the coordinator commit consume today. Then it runs fresh-process QC.
   - It must be deterministic and re-runnable on the same bag. The bag is the retained evidence.
3. **The live Recorder process** is removed from the run path once the pilot passes. Keep its modules only where the offline processor reuses them. Delete the live-only machinery (receiver threads, spool processes, start gate, deferred events, CAPTURING wait) in a cleanup step, with a cleanup TSV, backups and no skip/xfail.

## 4. Contract adjustments (allowed under CP-3394; each needs a change document)

Pilot first: the bag's receive timestamp, which is the record-only process's receipt, stands in for Recorder receipt time, so the existing rules stay as written. List every rule where this substitution is not exact; use `rec11-consistency.md` as the starting table.

At switch, rewrite the receipt-time rules on producer clocks: sim time, physics step, and the plugin's `handoff_monotonic_ns` / `publish_monotonic_ns` from CP-3411. This covers:
- "received before request" in source alignment;
- the world/scene 100 ms receipt join;
- any remaining delivery-age rule.

These stay unchanged:
- continuity and gap rules;
- session and epoch scope;
- the 10 Hz grid and the t+0.1 s label rule;
- the label source (`controller_state` reference);
- the endpoint rule `teacher_endpoint_v2`;
- the QC event order on sim time (verified reset ≤ first recorded instant ≤ first command ≤ normal_stop ≤ final);
- the lossless and seal requirements.

QC must also require that the bag covers the whole episode window with no per-source gaps.

## 5. Phases

Each phase follows the same order:
1. ledger PLANNED;
2. backup of every file before its first edit (tarball plus sha256, verified by extract/diff);
3. RED tests first;
4. GREEN;
5. the related test set;
6. ledger result.

### P0. Take over cleanly

1. Read §1 sources, `AGENTS.md` and the so101-dev skill.
2. Check `git -C <worktree> status --short | wc -l`, then `df -h /data`.
3. The previous writer (Claude subagent) was told to stop. Inspect the worktree for half-done round-13 edits made after freeze `TY1CPObX`: compare `src/` and `test/` against `$R/experiments/nonhead-installed-freeze.TY1CPObX/` (its source copy or source manifest). Keep a change only if it is complete and tested; otherwise restore it from the TY1CPObX copy. Record the decision.
4. **Disk:** if free space is below 300 GB, clean per §0. Candidates are listed in ledger CP-3366…CP-3427 "cleanup candidates":
   - freeze roots l14–l27 except TY1CPObX;
   - `scratch/b1-*`, `scratch/rec6-*`, `scratch/installed-*-colcon.*` older than the latest two of each gate;
   - `experiments/d5b-source-*`;
   - superseded `nonhead-qualified-inputs.*` dirs whose run is not retained;
   - `/tmp/so101-debug-*`.
5. Ledger entry CP: "Codex takeover".

### P1. Pilot recording (no change to the existing flow beyond the sidecar)

1. New tooling revision `TD/live-r4.zsh`, plus the matching new `run-qualified-live-20261007-r7.zsh`. They:
   - start `ros2 bag record -s mcap` with the topic list, QoS overrides and the scene poller;
   - wait for RECORDING;
   - run the existing flow;
   - stop the bag cleanly;
   - verify it with `ros2 bag info`.

   The bag goes to `<attempt dir>/raw/`, or `<live root>/raw/` if the attempt dir is not known before the run; then a symlink or manifest records where it is.
2. Measure the bag's throughput and size. Expect roughly 2 cameras × 10 Hz images, 500 Hz chunks and 3 × 500 Hz `controller_state`. Check the NVMe write headroom.
3. Run one L2 on a fresh freeze (cycle-r4 with the normal receipt; demo gate green twice). Expect the Teacher to PASS. The live Recorder outcome is irrelevant to the pilot.
4. Verify the bag:
   - per-topic counts;
   - per-source sequence continuity: world `publisher_sequence`, chunk sequence, event seq 1..N, and the `controller_state` stamp grid at 2 ms;
   - coverage from before the Teacher start to after `terminal`.

   Record it in the ledger.

### P2. Offline processor

1. Build `act/offline/`: a bag reader, the source interface, a driver over the existing modules, and a CLI `act_offline_episode` (setup.py entry) taking `--bag <dir> --inputs <inputs-manifest> --out <attempt sealed dir>` and producing the sealed episode, result facts and a processor report.
2. **Tests:**
   - RED/GREEN on a small synthetic MCAP built in the test with the real message types;
   - determinism (two runs give byte-identical output);
   - gap or missing topic → INVALID;
   - a source outside the window is ignored;
   - the QC event order;
   - label t+0.1 from `controller_state`.
3. Run it on the P1 pilot bag and iterate OFFLINE until the episode is VALID and fresh-process QC passes. Each fix gets a RED test from the real bag.
4. Write `rec-offline-pilot-report.md`: the rules whose receipt-time substitution was not exact, and the defects found.

### P3. Switch

Do this after P2 PASS on the pilot bag.

1. Write the design amendment `docs/superpowers/specs/2026-10-07-so101-act-raw-log-offline-amendment.md`. It covers the architecture, the contract changes per §4, the fault-case redefinition, and the cleanup inventory. Run an independent review by a fresh Codex session (`gpt-6.1-sol`, high) in another tmux window, reading only the spec and the code. Fix any findings.
2. **Implement:**
   - The orchestrator starts the bag recorder and waits for RECORDING (bounded), then starts the Teacher.
   - After `terminal`, it stops the bag and runs the offline processor, then ResultStore, coordinator commit and readback.
   - Remove the live Recorder from the run path.
   - Producer-clock rules per §4.
   - Fault injection redefined:
     - `recorder_absent` = no bag;
     - `recorder_late` = bag started after the Teacher's first command;
     - `queue_overflow` / `source_gap` = drop messages in the sandbox copy of the bag before processing;
     - `output_write_failure` = processor output dir read-only.

     Every fault case: Teacher PASS, data INVALID, rc 3.
3. Remove the live-only Recorder machinery per §3.3, with a cleanup TSV and backups.
4. Fresh freeze, all gates, demo gate green twice.

### P4. Live acceptance (base plan §5, one stack, serially)

- **L1, `off none`:** Teacher COMPLETED + PASS, data DISABLED, rc 0.
- **L2, `on none`:** Teacher PASS; the bag is complete; the offline processor gives VALID; fresh-process QC PASS; ResultStore commit and journal/index readback; export refused because the mode is diagnostic; rc 0. **This is the first-episode milestone.**
- **L3–L7** (redefined faults): Teacher PASS with no data-sourced cancel, data INVALID, rc 3.
- **Latency comparison:** Teacher phase-time median in L2–L7 against L1. Over 20% is reported, not hidden.

Record every run's input, expected and actual result, rc, logs, Teacher start/end pose, bag stats and cleanup proof.

### P5. Final report

Write task 6 of the base plan:
- Teacher result, data result, integration gate and live acceptance, reported separately;
- retained, archived and deletion-candidate evidence;
- remaining todo: Head and the formal quota are out of scope.

Put the report in the ledger and in `docs/superpowers/plans/changes/2026-10-07-final-report.md`. Static or unit GREEN is never presented as a live pass.

## 6. Gates and commands

- **Freeze + gates:** `zsh $TD/cycle-r4.zsh <tag> $R/calibration/r10b-20261007T034028Z/proposal.json $R/calibration/r10b-20261007T034028Z/activation-receipt.json`. The demo gate must pass twice: once in the cycle and once on a separate run of `run-qualified-gate-20261006-r8.zsh <F> demo-colcon`. Fix load-sensitive tests by isolating ROS domains (the conftest `isolated_ros_domain` exists); never loosen bounds.
- **Live:** `zsh $TD/live-r4.zsh <P> <F> on none` (after P1).
- **Known pre-existing failure:** `test_installed_provenance` in the dev runner only. It passes in the gate.
- **rg gate:** `$R/handoffs/teacher-act-decoupling-20261005.1RmsJ3ZJ/writer-artifacts/b3-rg-gate.zsh`.

## 7. Risks

- **Planning-scene coverage without service introspection:** the scene poller topic plus the Teacher's `scene_operation` CDR must be enough for source alignment. If not, write a change document.
- **Bag throughput and disk:** measure in P1.
- **The race moves to the bag start:** the bag must record before the Teacher's first command. RECORDING has no alignment precondition, so the bounded wait should be short.
- **QC rules relying on live-only facts:** list them in the pilot report.

## 8. Done criteria

- An L2 episode is VALID with QC PASS and committed.
- L1 and L3–L7 meet their expected results.
- The ledger and final report are written.
- Evidence is classified.
- No orphan processes; check `ps` for `ros2 bag`, `chunk_spool`, `controller_spool`, `ros2_control_node` and `move_group`.

## 9. Change-document format (`docs/superpowers/plans/changes/YYYY-MM-DD-<slug>.md`)

Each change document has:
- title;
- date;
- trigger (evidence with paths);
- options considered;
- the recommended option taken (citing CP-3394);
- contract impact;
- tests;
- rollback;
- the ledger CP id.

## 10. Handover state from the previous writer (2026-10-07, read before P0)

- Round 13 has no freeze; the last freeze is `TY1CPObX`. Round-13 backup: `$W/rec13-base.tar.gz` (+ `.sha256`), where `W=$R/handoffs/teacher-act-decoupling-20261005.1RmsJ3ZJ/writer-artifacts`.
- **Complete change:** `src/so101_demo_py/src/act/collection_boundaries.py`. It drops the 0.5 s upper bound in `validate_verified_reset`: a late join to the transient-local world topic replays old records, and every one of them failed that bound. That is what caused CP-3427's `COLLECTION_RESET_RECEIPT_INVALID` and the 8 s capture-start delay. It has 6 tests in `test/test_rec13_receipt.py`.
- **Reverted byte-for-byte:** `recorder_data_side.py`, `ros_episode_physics.py`, `episode_recorder_sources.py`.
- **New pilot code (untracked, partial):**
  - `src/so101_demo_py/src/act/offline/__init__.py`.
  - `bag_io.py`: bag metadata and read/write helpers (tested).
  - `raw_recorder.py`: the record-only process. It wraps `rosbag2_py.Recorder` with MCAP storage and code-derived topics. It has RECORDING readiness from graph info, wall/monotonic anchors, a 20 Hz `/get_planning_scene` sidecar (`scene-reads.jsonl`), and stats with a closed-bag check.
  - `test/test_rec13_raw_recorder.py`: 4 tests passing.
  - Untested: the sidecar poller, the `main()` CLI and signal handling.
  - The full test set was not run after these were added.
- **Facts:**
  - `rosbag2_py.Recorder.record()` returns immediately. Call `start_spin()` / `stop()` / `stop_spin()`, then drop the object so `metadata.yaml` is written.
  - rosbag2 stamps with the SYSTEM clock. Map bag stamps to monotonic through the recorded anchors (±~1 ms). That mapping is not exactly the Recorder's receipt.
  - move_group service introspection needs code changes, so use `scene_operation` CDR plus the sidecar reads.
  - `rosbag2_py` reads MCAP in the test venv. The python `mcap` module is not installed.
- **Known open live-Recorder issues (irrelevant once the switch is done):**
  - The initial-boundary search deep-copies on every pass, so passes stretch to 385–459 ms.
  - `ENDPOINT_INITIAL_CAPTURE_INVALID` race: the first world after the start waits for its chunk, up to 100 ms, which fails an estimated 15–25% of starts. The same exposure exists at final capture.
  - The offline processor removes both naturally. It still has to honour the endpoint-capture rules on producer clocks.
- **Processor sketch from the previous writer:**
  - Drive the real `RecorderEngine` / `RosRecorderSources` from bag replay with a fake node, so it takes the non-rclpy binding branch with no spooler processes.
  - Inject a virtual clock/sleep and patch `time.monotonic(_ns)`.
  - Make the executor inline and `spin_burst` a no-op.
  - Serve `/get_planning_scene` from the sidecar reads.
  - This is acceptable for the pilot. Note any rule that depends on wall pacing.
