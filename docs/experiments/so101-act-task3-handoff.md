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
