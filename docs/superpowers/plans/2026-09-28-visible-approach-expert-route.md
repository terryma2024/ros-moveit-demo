# Visible Approach Expert Route Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualify the first visible approach prefix for an expert route using the selected SEARCH source and one complete PathProof.

**Architecture:** Keep the checked diagnostic candidate as an input, with its collection flag unchanged. A new verifier freezes a separate expert template, accepts a SEARCH observation only when its physical, reference, owner and native ingress proofs match, and prepares the first exact 600-row prefix. A second check accepts only a broker-private source receipt and a SAFE 701-sample PathProof for that same prefix. The resulting qualification still needs a permit and later commit-window recheck before a goal.

**Tech Stack:** Python 3.12, MuJoCo 3.12.0, ROS 2 Jazzy, pytest.

**Spec:** `docs/experiments/so101-act-data-experiment-ledger.md`, CP-546, CP-556 and EXP-533; `docs/superpowers/specs/2026-09-27-so101-act-path-proof-control-rate-design.md`.

## Global Constraints

- Use `/data/work/so101-evidence/act-data/20260924-fbc25063-resume`, the current worktree and branch. Do not stage unrelated dirty files.
- Use business names in new source. Keep all existing diagnostic manifests at `eligible_for_collection=False`.
- Run each pytest or colcon gate with a new verified `/data` scratch and the exact `test-venv/bin/python`. The ordinary Python gate excludes `benchmark_test`.
- Do not run the EXP-469 performance program, start a stack, reset, submit a goal, move hardware, or count a formal episode.

## Review Focus

- A SEARCH proof for an older selected source must fail even when its model matches. Test changed source hash in each proof.
- Native ingress after stop or a changed owner generation must fail. Test the recorded native proof and ticket fields.
- A forged positive flag on the diagnostic candidate must not become a route qualification. Test the candidate input and separate template digest.
- A SAFE proof for changed rows, source receipt, policy or physical state must fail. Test each PathProof binding.
- A partial or violated checker result must not qualify. Test sample count 700 and `VIOLATION`.

---

### Task 1: Freeze a source-bound expert template

**Files:**
- Create: `src/so101_demo_py/src/adapters/act/visible_approach_expert_route.py`
- Test: `src/so101_demo_py/test/test_act_visible_approach_expert_route.py`

**Interfaces:**
- Consumes: `SelectedApproachCandidate.prepare(observed, selected_source=...)` and the four SEARCH proofs.
- Produces: `VisibleApproachExpertRoute(candidate, *, policy_fingerprint, monotonic)` with `prepare(observed, *, selected_source, owner_ticket, active_policy_fingerprint) -> dict` and a read-only `manifest` property.

- [ ] Write tests for a valid first prefix and all Task 1 Review Focus mismatches. Require a new `VISIBLE_APPROACH_EXPERT_TEMPLATE` digest that pins source candidate, compiled model, scene, activated policy, first-group rows and 2 ms/2 mm limits. Assert preparation has no command or collection authority.
- [ ] Run focused tests to RED at the missing new module.
- [ ] Implement the template and proof-chain validator. Recheck the selected source after candidate preparation and reject stale or changed ticket, policy, source, row hash or proof fields. Preserve the original candidate flags.
- [ ] Run focused tests to GREEN and commit source plus tests.

### Task 2: Require one complete PathProof before route qualification

**Files:**
- Modify: `src/so101_demo_py/src/adapters/act/visible_approach_expert_route.py`
- Test: `src/so101_demo_py/test/test_act_visible_approach_expert_route.py`

**Interfaces:**
- Consumes: the prepared template, `PrefixSourceReceipt` and `PathProof`.
- Produces: `VisibleApproachExpertRoute.qualify(prepared, proof, *, current_snapshot) -> dict`.

- [ ] Write tests using the real `MujocoPathChecker` and `PathProver`. One exact SAFE 701-sample first prefix qualifies; changed rows, receipt, generation, policy, state, a 700-sample result or `VIOLATION` refuses. Assert one full checker call per qualification.
- [ ] Run focused tests to RED at the missing `qualify` method.
- [ ] Implement exact receipt, prefix, manifest and state comparisons. Return a separate `route_qualified=True` result with `command_authority=False` and `permit_required=True`; do not mutate the prepared candidate or issue a goal.
- [ ] Run focused tests to GREEN. Run complete ordinary `so101_demo_py` source and installed gates, check JUnit/test-result and source/build hashes, then commit code and checkpoint the ledger.
