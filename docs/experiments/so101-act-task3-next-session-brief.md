# Task 3 — brief for the next session (written 2026-09-30, handoff requested by the owner)

Read this first; it supersedes the older sections of `so101-act-task3-handoff.md` where they disagree. The
ledger (`so101-act-data-experiment-ledger.md`, CP-1921 … CP-2063) is the full record with every RED/GREEN
pointer. Verified position: HEAD `36df61a74`, targeted parallel gate `logs/task3-gate17.run` **419 passed**.

## 1. Where you are working

- Worktree `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a`, branch
  `codex/so101-act-data-0917a`, on ai-station. Do not create a new worktree or branch.
- `source /data/work/so101-evidence/act-data/20260924-fbc25063-resume/experiments/nonhead-first-episode-plan.hKhvkON3/env.zsh`
  sets `TASK_ROOT`, `PLAN_ROOT`, `TEST_PYTHON` and the live-source `PYTHONPATH`.
- Every pytest run: fresh NVMe scratch under `$TASK_ROOT/scratch/`, `TMPDIR`/`TMP`/`TEMP` pointed at it, and
  the tempfile proof run with `$TEST_PYTHON` itself. Run the gate under `pytest-xdist` with
  `min(8, logical CPUs)` workers — the SO-101 skill requires the parallel form; serial runs are localisation
  only.
- **Staging rule (do not repeat a mistake recorded in CP-2026).** Before staging any file the session-start
  baseline lists as dirty, check it against the backups first:
  `git diff /data/work/so101-evidence/act-data/20260924-fbc25063-resume/experiments/nonhead-first-episode-plan.hKhvkON3/baseline-task3/<flattened-name> <path>`.
  An empty diff means you may stage the whole file; otherwise use `git add -p`. 24 tracked and 13 untracked
  paths remain from before this work and must be preserved.
- Never push, never delete evidence, never touch hardware, never start a second stack.

## 2. The four items left in Task 3

**(a) Let the full `planning_scene_observation` record travel — only the producer is missing.** The port
produces it (`RosTaskScenePort.observe_observation()`, CP-2020), the document carries it additively when
supplied (CP-2028) and that channel is proved in both directions (CP-2067). **The reader is the
observation attribute** — `_search_evidence` reads `getattr(observed, "planning_scene_observation", None)`
and `PickPlaceSearchObservation` now declares that field (CP-2066) — so the record must be set on the
**observation object**, not in the readback's raw mapping: a correction to CP-2075, which first suggested
`raw["observation"]` before this round re-read the reader. Missing is the producer: the place that builds
the observation (the boundary's search path, which is also where `self.planning_scene` lives) fills the
field from `observe_observation()` plus the simulation instant it owns, after which the audit's end-to-end
verification of the full record applies.

**(b) Three-way controls - narrowed by CP-2069/CP-2070, and it is now about the boundary only.** The
port's gates are no longer derived: its own validation refuses a non-locking result, a truncated world,
contact evidence from another step and any stamp outside `skew` before the document exists, so those four
are stated with a reason block and a control for them would only test the validator. What still lacks a
control is the **boundary's `controller_reference_ok` and `planning_ok`** (the scene and feedback gates
have theirs at CP-2036/CP-2044 via `_case(..., receipt=..., feedback=...)`): add `reference=`/`planning=`
parameters to `_case` in `test_act_task8_motion_phases.py` (line 29) and assert the document's values
for a present, an absent and a wrong-shape proof, mirroring CP-2044.

**(c) T3-F11's window-to-rows and observed-schedule checks.** Two attempts reverted (CP-1997, CP-2001),
so the checks are not in the code. What went wrong both times: the fixtures were written by hand with a
window that did not match what the audit actually held, so the check under test was not the one that fired
— the coverage gate refused first once, and the observed-schedule rule refused the hand-written schedule
the other time. Build them the other way round: mint the acquisitions the window will declare, bind a row,
then **derive** `label_cutoff_s`, `collection_start_s`, `collection_end_s` and `physics_end_s` from those
values behind one self-consistent formal-episode helper, and make every check a one-line variant of it.

**(c) T3-F11 — one pass, four edits that must land together.** Do not try the module alone: the existing
formal fixtures (`_formal_writer` + `_window(...)`) do not yet describe the rows and acquisitions they hold, so
the matcher alone turns them red — that is exactly how CP-1997/CP-2001 reverted.
1. In `episode_audit.py`, add `_window_matches_rows` (the body is in CP-1997; the rules are: a `complete`
   outcome needs at least one bound row whose instant the cutoff equals, another outcome may not accompany rows,
   every `streams_required` entry must appear in `source_schedule`, every scheduled instant must be one the
   audit actually holds for that camera, and a gap beyond 1.5 cadences must be a permitted one).
2. Call it from `seal()`'s formal-window gate — **line 789** is where that gate raises `AUDIT_WINDOW_INVALID`;
   insert after the enclosing `if` block (the gate is a single condition since CP-2006), not after the raise.
3. Track the bound row instants (`self._row_times`) beside `self._row_indexes`.
4. Extend the formal fixtures in `test_act_episode_audit.py` **from the audit's own contents** with the
   acquisition/row/source sequence of CP-2078, deriving the window from those values, and make each check a
   one-line variant — including the negative cases: cutoff not the row's instant, a scheduled instant with no
   acquisition, an unpemitted gap beyond 1.5 cadences, a required stream missing, an instant outside the window.
Then run the audit suite plus the twenty-file gate.

**(d) A fresh checkpoint after (a)-(c).** The plan's checkpoint reviewers are GPT-6.1 Sol / High via a Codex
session in tmux; the fifth verdict is `reviews/task3-rereview4-verdict.md` (FAIL, 6 Important, all since
closed except the items above). Prepare a packet like `reviews/task3-review5-packet.md`, including the
ratified schemas, this brief, the gate pointer and the verdict file to write.

## 3. Patterns that work here, and the ones that cost whole rounds

- **Extend an existing parametrisation or assertion block.** Every increment that landed first-try did this
  (CP-1999, CP-2000, CP-2003, CP-2005-2007, CP-2012, CP-2029, CP-2034, CP-2043, CP-2048, CP-2050, CP-2052,
  CP-2055, CP-2056, CP-2058, CP-2059). Five attempts that needed a **new** fixture consistent with the
  module's invariants reverted (CP-1961, CP-1993, CP-1994, CP-1997, CP-2001) — read the test file first.
- **Locate by structure, assert the exact line, print the neighbourhood** (CP-2043). Anchoring on
  half-remembered text cost a round (CP-2042), and an insertion can land **between a decorator and its
  method** (CP-2033 caught that; always print the neighbouring lines after such a patch).
- **A patch script should write only after every assertion passes**, so a failed anchor leaves the file
  untouched (CP-2042's safe failure).
- Writers create their own root: a fixture creates only the **parent** directory.

## 4. Documented choices and open semantics

- `scene_revision` is the scene port's own successful-read counter (CP-2020, because MoveIt's `PlanningScene`
  message has none); `status_sequence` is the broker's own feedback-read counter (CP-2040, because the action
  status list has none); the two camera gates are **freshness** (CP-2059). Each is implemented in one place and
  the owner may amend it.
- The SEARCH document's `planning_ok` is deliberately **not** derived: the port refuses a non-locking result
  first, so a derivation would be a decorated literal (CP-2061/CP-2062). Making it real means giving it a
  source (the boundary's path/approval evidence), which is an owner-level choice.
- Gate accounting, corrected at CP-2070: the **boundary helper's four** gates are derived from things that can
  genuinely be absent (the scene receipt, the controller records, the reference proof, the path proof) and two of
  them have three-way controls; the **SEARCH document** derives three (`planning_scene_ok`,
  `controller_reference_ok`, `joint_feedback_ok`) and states the rest explicitly, because the port's own
  validation refuses a non-locking result, a truncated world, contact evidence from another step and any stamp
  outside `skew` before the document exists (CP-2069). Nothing in either place claims a gate it did not observe
  or cannot vary.

## 5. What the objective still needs after Task 3

Tasks 4-8: independent QC with its own verifier and receipts; the production composition and installed CLI;
the freeze/build/integration gates (start with a fresh `colcon build --install-base`, because the full module
scope cannot even be collected in the live-source environment — CP-2002, and the measured baseline is
5654 passed / 321 failed / 155 skipped / 10 errors, dominated by that missing overlay, CP-2022/CP-2023); one
real `FULL_RESTART` MuJoCo pick-and-place with the Recorder's lossless files; and the negative-copy delivery
step. The four real input roles (`path_policy`, `placement_qc`, `rgb_skew`, `resource_thresholds`) still need
approved values before Tasks 6/7 can run.


---

# TASK 4 HANDOFF (added round 169) — what exists, what is left, and the rule that settles the last failure

**Landed already (three increments, all green).** `src/so101_demo_py/src/act/w8_qualification.py` now provides
`verify_w8_qualification(qualified_path, payload)`: it requires a `QUALIFIED` document with `worker_count == 8`
and a `live_campaign` block of exactly four keys, **re-derives** the campaign-result and journal digests from
disk, passes the campaign result through `validate_campaign_summary` and requires its digests to equal the
document's, and — when the payload names a preparation receipt — opens that bundle and delegates the fourteen
case journals to `validate_case_journals` with the bundle's identities. Refusals are
`W8_QUALIFICATION_EVIDENCE_INVALID` and `W8_QUALIFICATION_EVIDENCE_MISMATCH`. `so101_teleop`'s admission now
reaches this verifier instead of failing with `W8_QUALIFICATION_VERIFIER_UNAVAILABLE`, and its
self-declared-PASSED test was updated to the verifier's refusal code with the reason in the test.

**Left in Task 4, in order.**
1. **The qualification suite's evidence port** (`test_act_task8_live_qualification.py`, four failures traced in
   CP-2089 to the amended fail-closed contract — not to the environment). The runner records `_missing_raw` in
   `_physics` (`pick_place_runner.py:109-120`) whenever a phase's evidence lacks `physical_observation`, and that
   list is what makes `live_evidence_artifact` `None`. Three attempts to supply it by wrapping `run_phase`'s
   funnel return failed identically (CP-2091/2092/2096), so **read those four tests' bodies and the port
   methods they actually drive before wrapping anything**; the SEARCH document already carries the key additively
   (CP-2028) and the set-down document refuses it (CP-2091).
2. **The verifier's positive test**: a committed prepared bundle (`test_act_task8_artifact_bundle.py:34-86`'s
   `ValidInputs`/`_inputs` is the model) plus fourteen journals that satisfy `validate_case_journals` — the
   journals come from the suite in item 1, so the two are one increment (CP-2095).
3. **Then**: with the qualification path green, confirm the live production composition actually uses the
   commit/export-refusal apparatus (`act/result_store.py`, `test_act_result_commit.py`) — item 4's second half.
4. **Settle with the owner or the frozen plan**: the admission comment assigns the independent verifier to
   **Task 11A** ("Task 11A must provide an independent verifier …"), while this objective's frozen enumeration
   calls item 4 "independent QC / real commit / export refusal" (CP-2087).

**Still unresolved from Task 3's own list.** Item 3 is implementation-complete (T3-F11 landed, gate
`logs/task3-final.run` **430 passed**) but its **sixth checkpoint's verdict has not appeared** across many
rounds (`reviews/task3-rereview5-verdict.md`, dispatch `32c54563-a7b4-438d-bfc1-620b13d28b6e`); nothing should
be claimed about Task 3's closure until that file exists and is read.
