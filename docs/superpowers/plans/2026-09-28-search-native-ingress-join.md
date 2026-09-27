# SEARCH Native Controller Ingress Join Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind a selected, stopped SEARCH source to authenticated arm, gripper and neck action ingress snapshots.

**Architecture:** Keep the native socket query in `ControllerReservationClient`. A separate verifier reads all three snapshots after the selected source receipts and binds them to the existing physics, reference and local owner proofs. The SEARCH segment requires that verifier before returning. This proof does not grant a goal permit; the commit window must query the native controllers again.

**Tech Stack:** Python 3.12, ROS 2 Jazzy, pytest, existing `so101_demo_py` overlay.

**Spec:** `docs/experiments/so101-act-data-experiment-ledger.md`, EXP-531 and CP-555; approved PathProof and commit-window specification in `/data/work/so101-evidence/act-data/20260924-fbc25063-resume/handoff/2026-09-27-path-proof-control-rate-handoff.md`.

## Global Constraints

- Use the registered evidence root `/data/work/so101-evidence/act-data/20260924-fbc25063-resume` and the current worktree and branch. Keep other dirty files intact.
- Run source and installed ordinary package tests with fresh `/data` scratch, verified `TMPDIR/TMP/TEMP`, and the exact `test-venv/bin/python`. Do not collect `benchmark_test`.
- Do not start a stack, reset, submit a goal, move hardware, or count a formal episode in this source experiment.
- Keep `command_authority=False` and `eligible_for_collection=False` until the later commit-window and route gates pass.

## Review Focus

- A controller callback after stop but before a query must close SEARCH. Test the last ingress timestamp on each role.
- A reply observed before the selected source's latest original receipt must close SEARCH. Test the maximum receipt across all seven source kinds.
- A wrong generation, role, or changed owner/source proof must close SEARCH. Test each mismatch at the verifier boundary.
- A stale, future, missing, or malformed snapshot must close SEARCH. Test exact fields, monotonic order and the existing source age bound.
- A native query failure or changed SEARCH scope must stop the segment. Test the failure path and the production boundary wiring.

---

### Task 1: Verify the three native snapshots

**Files:**
- Create: `src/so101_demo_py/src/adapters/act/pick_place_search_native_ingress.py`
- Test: `src/so101_demo_py/test/test_act_pick_place_search_native_ingress.py`

**Interfaces:**
- Consumes: `ControllerReservationClient.snapshot_generation(ticket, kind)`, `freeze_selected_search_source`, and the physics, reference and local owner proofs.
- Produces: `verify_search_native_controller_ingress(broker, ticket, sources, observed, physical_proof, reference_proof, owner_proof, *, stopped_wall_s) -> dict`.

- [ ] Write tests for a valid three-role join and for the five Review Focus cases owned by this verifier. Assert `command_authority is False`, `eligible_for_collection is False`, exact selected source and owner hashes, generation, and a deterministic snapshot digest.
- [ ] Run the focused tests and retain the intended RED at the missing verifier import.
- [ ] Implement the verifier. Require the same selected source hash, stop time and owner generation across inputs. Validate exact snapshot keys and types, each role once, each `last_ingress_monotonic_ns <= stop_ns`, each `observed_monotonic_ns >= max(original source receipts)`, `last <= observed <= received <= now`, and `now - received <= sources.readback.max_wall_age`. Recheck ticket, armed generation, stopped driver, SEARCH scope and selected source after the queries. Hash the validated snapshots with a versioned prefix. Return a neutral proof that explicitly requires commit-window ingress recheck.
- [ ] Run the focused tests to GREEN and commit the verifier with its tests.

### Task 2: Require the join in production SEARCH

**Files:**
- Modify: `src/so101_demo_py/src/adapters/act/pick_place_search_segment.py`
- Modify: `src/so101_demo_py/src/adapters/act/pick_place_search_boundary.py`
- Test: `src/so101_demo_py/test/test_act_task8_search_segment.py`
- Test: `src/so101_demo_py/test/test_act_pick_place_search_native_ingress.py`

**Interfaces:**
- Consumes: `verify_search_native_controller_ingress(...)` from Task 1.
- Produces: `PickPlaceSearchObservation.native_controller_ingress_proof` and a required `native_ingress_verifier` callback in `PickPlaceSearchSegment`.

- [ ] Write tests showing that SEARCH refuses a missing/invalid native proof, confirms stop on failure, and returns the bound proof on success. Test that the production boundary passes its current ticket and the real verifier.
- [ ] Run those tests to RED at the missing segment constructor argument or proof field.
- [ ] Call the native verifier after the local owner verifier. Check its selected source, owner event hash, stop time, generation and neutral flags before returning. Have the boundary construct the callback with its current broker ticket.
- [ ] Run focused tests to GREEN, then the full source and installed ordinary `so101_demo_py` gates. Check package XML, test-result, formatting and installed/source identity; commit source and checkpoint the evidence in the experiment ledger.
