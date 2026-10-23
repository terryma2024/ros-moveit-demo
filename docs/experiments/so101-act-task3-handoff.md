# Task 3 resumption handoff (2026-09-30, after 30+ instalments)

Written for whoever continues `dst` execution in this worktree. The ledger
(`docs/experiments/so101-act-data-experiment-ledger.md`, CP-1921 … CP-1997) holds the full history; this
file is the shortest path back to working state. Everything below is verified against the worktree at HEAD
`4b8e0485a`, gate `logs/task3-gate9.run` **410 passed in 26.67s** (previous checkpoints: 403 at the fifth verdict, 410 at
CP-2004; the figure rises as controls are added)

## Where Task 3 actually stands

Closed and green: the common raw audit writer (exclusive root, closed streams, seal-once, recomputation
verification), the release boundary with the tests that were missing, Recorder seal v2 with
`audit_manifest_sha256`/`scope_sha256`, the runner's real phase events, the registered physics live sample
(admitted and validated), the ratified collection window for formal audits, Proposal A's per-frame reference
schema at the audit boundary plus the observer sequence and the broker's per-kind names, the two ratified
records (`planning_scene_observation`, `controller_feedback`) with their parent-instant join, the
fail-closed formal gates (`formal_episode_eligible: False` without raw evidence; no formal seal without
coverage), and the four checkpoint rounds' findings except those listed below.

Open, in the order I would attack them:

1. **T3-F1's producer side.** Nothing returns the ratified records yet: `ros_broker.py::reference_state`
   still returns a fused six-joint projection, and the two helpers that assert `planning_scene_ok: True`
   (`pick_place_search_port.py:412`, `pick_place_search_boundary.py:282`) do not derive their gates from
   records. The owner has ratified the schemas and explicitly authorised replacing those literals with real
   observations.
2. **Amendment A.1, awaiting the owner.** The reviewer recommends per-kind evaluation **and** warns that
   moving `evaluation` alone is not enough: the projected values currently must equal the *published*
   positions, while an interval evaluation at a later target may legitimately differ. The amendment must
   distinguish per-kind **evaluated** positions from the original **published** positions and state which the
   projection map selects.
3. **T3-F3 / T3-F5 readback residuals.** Readback must refuse a reference record carrying keys from both raw
   groups, and re-apply the formal coverage gate; CP-1993 records the exact recipe.
4. **T3-F11's window-to-rows and observed-schedule checks.** CP-1997 and CP-2001 record the two attempts and
   the recipe: build the fixtures from the audit's own contents (mint the acquisitions the window declares,
   bind a row, then derive the window fields) behind a single self-consistent formal-episode helper. Both
   attempts reverted, so the checks are not in the code yet.

Already landed since the fifth verdict: readback refusing both raw reference groups (CP-1999), the formal
coverage gate re-applied on readback (CP-2000), five more re-signed counterexamples covering readback checks
that had none (CP-2003), and the observer counter's off-by-one fix with its control (CP-1995).

## The fixture lesson, stated once

Four instalments were reverted because a *control* could not be built inside the round's budget (CP-1961,
CP-1993, CP-1994, CP-1997). Every one of them was fixed by reading the existing test file first. Concretely:

- `test_act_recorder.py` has `observation(at_s)`, `audit(at_s, ...)`, `outcome(status)`, `PROVENANCE`, and
  `_multi_row_audit`/`_three_row_recorder` which already pair a real multi-row episode with a matching audit.
- `test_act_episode_audit.py` has `scope()`, `identity()`, `_lease()`, `_window()`, `_formal_writer`,
  `complete_audit`, `_staging` and `_resign(writer, manifest_path, name, payload)` for checksum-consistent
  tampering.
- `test_act_controller_reference_observer.py` has `frame(stamp_ns, *, names=...)` and `recent()` returns
  `(identity, rows)`.
- Writers create their own root, so a fixture must create only the **parent** directory.

## Environment

- Worktree `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a`, branch
  `codex/so101-act-data-0917a`; plan and ledger under `docs/experiments/` and `docs/superpowers/plans/`.
- `env.zsh` in `.../experiments/nonhead-first-episode-plan.hKhvkON3/` sets `TASK_ROOT`, `PLAN_ROOT`,
  `TEST_PYTHON` and the live-source `PYTHONPATH`; every run needs a fresh NVMe scratch with
  `TMPDIR`/`TMP`/`TEMP` set and a tempfile proof.
- Evidence root: `/data/work/so101-evidence/act-data/20260924-fbc25063-resume`. The four real input roles
  (`path_policy`, `placement_qc`, `rgb_skew`, `resource_thresholds`) still have no approved values, which
  Task 6/7 need.

## What the objective still requires

Tasks 4 to 8: independent QC with its own verifier and receipts, the default production composition and
installed CLI, the freeze/build/integration gates, one real `FULL_RESTART` MuJoCo pick-and-place with the
Recorder's lossless files, and the negative-copy delivery step. None of them start before the owner decides
between converging Task 3 further (A.1 plus the producer wiring) and freezing Task 3 in its current
fail-closed state to begin Task 4.

---

# UPDATE 2026-09-30 (later) — supersedes the sections above where they disagree

Verified against HEAD `4be0018ef`; targeted gate `logs/task3-xdist.run` **410 passed under `pytest-xdist`
(8 workers on 32 CPUs)**, which is the gate form the SO-101 skill requires — the serial figures quoted earlier
in this file (403/410 in 26 s) were localisation runs, not gates.

## Closed since the first version of this file

- **Amendment A.1, ratified by the owner**, is implemented at the audit boundary, the tap, the capture and the
  broker's data side: each frame carries its immutable `published_positions`/`published_velocities` beside
  `evaluated_positions`/`evaluated_velocities` for the record's target instant, with a **per-kind**
  `evaluation {requested_sim_time_s, basis, goal_id, accepted_sim_s, revoked_sim_s}`, and the record-level
  `projection_map` **selects the evaluated values** (the owner's explicit choice). The broker serves both bases
  through `reference_frames(kind, when)`; `reference_state` keeps the fused projection as the compatibility path.
- **Readback exclusivity** for the two raw reference groups (CP-1999) and the **formal coverage gate on
  readback** (CP-2000); five more re-signed counterexamples (CP-2003); the observer counter's off-by-one fix
  with its 60-publication control (CP-1995); three more ratified-window rules (CP-2005/2006/2007).
- **Producer step 1 of 4** (CP-2017/CP-2020): `RosTaskScenePort.observe_observation()` returns the record's
  parts — sorted attached and world ids, `is_diff`, `source`, and `scene_revision` as the port's **own
  documented read counter**, because MoveIt's `PlanningScene` message has no revision field (CP-2019).

## Open, with the exact wiring

1. **Producer steps 2-4.** Step 2: the readback that establishes the eight gates returns
   `planning_scene_observation` (and `controller_feedback` from the controller status it already reads).
   Step 3: `_gate_facts` (`pick_place_search_boundary.py:272`, called at `:308` in `sequence_facts` and `:402`
   in `set_down`) **derives** `planning_scene_ok`/`joint_feedback_ok`/`controller_reference_ok` from those
   records on the same instant; the literal is a **documented caller-supplied placeholder** (`:303-306`), and
   the supplier is the SEARCH validation (`search()` at `:739`), which should store the validated receipt and
   its instant on the boundary. Port side: the literal sits at `pick_place_search_port.py:412` inside
   `_search_evidence` (`:313`). Step 4: keep the **six** phase-document tests green (CP-2016 names them) and
   add controls for a missing or off-instant record.
2. **Consumer half of A.1**: callers still read `reference_state`'s fused projection.
3. **T3-F11's window-to-rows checks** (reverted twice; recipes in CP-1997/CP-2001).
4. **`scene_revision`'s meaning** — option (a) is implemented; the owner may prefer amending the field.

## Recipes and environment (unchanged from above, restated once)

Extend an existing parametrisation or assertion block rather than building a new fixture (six first-try
landings versus five reverts). Reusable helpers live in `test_act_recorder.py`, `test_act_episode_audit.py`,
`test_act_controller_reference_observer.py` and `test_act_task8_search_port.py`; writers create their own root,
so a fixture creates only the parent. Every run needs a fresh NVMe scratch with `TMPDIR`/`TMP`/`TEMP` and a
tempfile proof. The **full module scope cannot be collected** here until Task 6 builds an install overlay
(CP-2002), so the xdist gate covers the checkpoint's twenty files plus the observer suite.

---

# UPDATE 2026-09-30 (final) — worktree integrity, and the staging rule that prevents a repeat

## What happened

`pick_place_runner.py` had **46 lines of uncommitted work** at session start (`"physics_step"` added to the
phase and set-down key sets, `def set_down(...)`, `_SET_DOWN_KEYS`). Because I staged that file whole
(`git add <file>`), the first commit of mine touching it (`dcef92f99`) carried those 46 lines into git
together with my own edits. The bytes are not lost — they are in the tree and now in history — but they no
longer appear as uncommitted changes and they sit inside my commit rather than the author's.

Verified the other four baseline files are intact: `recorder.py`'s backup is byte-identical to the parent of
the first commit of mine that touched it (so nothing was swept there), `pick_place_sources.py` and
`test_act_task8_reset.py` are still modified and byte-identical to their backups, and
`pick_place_search_port.py` is byte-identical to its backup. **No history was rewritten.**

## Options for the owner (nothing is urgent, since no bytes were lost)

1. Leave it, accepting that history records *what* changed but not who first wrote those 46 lines.
2. Reproduce the original state: revert only those hunks for that file to `b0832129e` and leave them
   uncommitted again. My later edits sit on the same regions, so this needs care plus a green acceptance run.
3. Split attribution with a small follow-up commit (for example `--author` on the recovered lines) without
   rewriting history.

## Rule for every future pass in this worktree

Before staging **any** file that the session-start baseline lists as dirty, either `git add -p` and stage
hunks, or check it against the recorded backups first:

```
git diff /data/work/so101-evidence/act-data/20260924-fbc25063-resume/experiments/nonhead-first-episode-plan.hKhvkON3/baseline-task3/<flattened-name> <path>
```

An empty diff means the file is safe to stage whole. The backups are flattened as
`src_so101_demo_py_src_act_recorder.py` and so on.

## Where the numbers stand

- Targeted parallel gate (the checkpoint's twenty files plus the observer suite): `logs/task3-xdist.run`,
  **410 passed**, xdist with 8 workers on 32 CPUs — the trustworthy green figure for this objective's boundary.
- Ordinary module scope, first measurement (CP-2022): **5654 passed / 321 failed / 155 skipped / 10 errors**
  with the un-collectable entrypoint file ignored, dominated by the missing install overlay (1555
  `PackageNotFoundError` markers, CP-2023 confirmed the ACT-related entries fail at fixture setup); Task 6
  re-runs that exact command after building the overlay and treats the delta as the regression surface.
- Producer change's acceptance set (CP-2024), all green today by name: the micro-lift, release and
  radial-retreat tests in `test_act_task8_motion_phases.py`, the dispatch test in
  `test_act_task8_close_execution.py`, and the final-check pair.

---

# UPDATE 2026-09-30 (milestone) — no gate is asserted on the live path any more

At HEAD `42d8ac443`, consolidated gate `logs/task3-gate16.run` **419 passed in 10.47s** (xdist, 8 workers on 32 CPUs):

- **Twelve gates are derived from observations the search established**, and neither the boundary helper nor
  the SEARCH document asserts one: the path proof (`planning_ok`), the reference verifier's own proof
  (`controller_reference_ok`), the verified scene receipt (`planning_scene_ok`), the ratified controller
  records at the world's instant (`joint_feedback_ok`), the contact evidence's step join (`contact_ok`),
  the world not being truncated (`mujoco_ok`), the search result's own verdict (`planning_ok` in the
  document) and each camera's stamp freshness (`head_rgb_ok`/`wrist_rgb_ok`).
- **Three documented choices** were made where the plan did not decide, each revisitable in one place:
  `scene_revision` is the scene port's own read counter (CP-2020), `status_sequence` is the broker's own
  feedback-read counter (CP-2040), and the camera gates are freshness (CP-2059).
- **Still open for Task 3**: the full `planning_scene_observation` record's travel once the readback fills
  it; three-way controls for the gates that lack them; T3-F11's window-to-rows checks (CP-1997/CP-2001); then
  a fresh checkpoint. Tasks 4-8 have not started, and the four real input roles still need approved values.
