# Exact native IK loop implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, task by task. User approved this approach and requested goal execution; do not delegate or launch dst.

**Goal:** Reduce the current native prepare_horizon median by at least 50% on the same isolated ai-station P core, retaining exact outputs and finite-difference updates.

**Architecture:** Extend the existing Cython kernel to own the complete iteration loop and per-call workspaces. Keep the current NumPy matrix product and linear solve arithmetic. Batch path FK only after the solver passes differential validation.

**Tech Stack:** Cython 3.3.0 generated C, existing NumPy, CPython, normal setuptools/colcon install.

**Spec:** The approved conversation proposal (full native loop, workspace reuse, path FK) and CP-016 in docs/experiments/prepare-horizon-ik-20261004-01a10735-experiment-ledger.md.

## Global constraints

- One evidence root: /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735. All new artifacts in loop50; retain every attempt.
- Current task worktree and codex branch only. No shared overlay, environment, old checkout, simulation or physics changes.
- Inline Codex gpt-6.1-sol/xhigh; no agents/dst. Existing authorization supersedes default skill/model execution recommendations.
- CPU14 only, SMT15 reserved idle, one compute/BLAS thread. Temporary cgroup partition must restore all masks afterward.
- Frozen four fixtures, equal weights, original unchanged timer harness, 14 waypoints, beam3, seeds/order/gates/scoring/9 samples unchanged.
- Finite differences, damping1e-5, epsilon1e-5, 200 iterations, step cap0.20 and margins unchanged.
- Exact full documents, errors and lossless update traces. No analytic Jacobian, changed solver, approximate cache or floating tolerance relaxation.
- Formal A/B: B0,O0,O1,B1,B2,O2, three fresh processes/variant, one warmup and five samples/fixture/process. Ratio<=0.50; report absolute target259.632309ms as well.

## Task 1: current Linux baseline and separate profile

- [x] Freeze source296620330, harness and fixture hashes; confirm retained private install.
- [x] Register EXP-024 before execution; run current baseline and independent profile under temporary isolated P14/P15 partition.
- [x] Copy all raw artifacts back; check exact full outputs and CPU restoration.

## Task 2: complete native iteration

**Files:** _ik_numeric.pyx / generated _ik_numeric.c, underactuated_ik.py, test_ik_numeric_kernel.py.

**Interfaces:** Existing solve signature/results unchanged. New internal NumericKernel.solve returns success flag and final positions; wrapper retains final failure formatting. Subclasses, duplicate joint layouts, unsupported dtypes/nonfinite inputs and customized instance hooks retain existing path.

- [x] RED: compare optimized and reference outcomes plus all np.linalg.solve lhs/rhs/raw step bytes, and assert the full-loop capability exists before numerical comparison:

```python
assert hasattr(solver._numeric, "solve"), "native solve loop is missing"
```

- [x] Implement the 200-step control loop in Cython with original products/solve/clip. Build a new private extension; shared runtime needs no Cython.
- [x] Avoid quaternion/Pose construction on finite iterations whose position gate already fails. Preserve validation/error behavior and orientation computation when its gate is evaluated.
- [x] GREEN: immediate success, failed200 iterations, signed zero, limits, arbitrary axes/order, nextafter gates and fallback cases; run 64-case independent lossless differential.
- [x] Separate exploratory full-horizon timing and exact outputs; retain source snapshot and hashes before further changes.

## Task 3: reusable per-solve workspace

**Files:** _ik_numeric.pyx / generated C and numeric tests.

**Interfaces:** Buffers are invocation-local, never returned as mutable shared state; residual/Jacobian public methods preserve existing ownership and guards.

- [x] RED: repeated numeric evaluation must match reference bytes and retain prior results; allocation observations must show bounded workspace construction independent of iteration count.
- [x] Reuse motions, prefixes, candidate residual and Jacobian buffers. Retain NumPy product/reduction semantics; test every changed operation independently.
- [x] GREEN: complete solver traces and horizon documents, including failures; independent exploratory timing.

## Task 4: path FK specialization

**Files:** deterministic_horizon.py, underactuated_ik.py, _ik_numeric.pyx / generated C, horizon/numeric tests.

**Interfaces:** Internal batch position access retains endpoint and nine interpolated points, sample order and exact arithmetic. Custom IK implementations continue through forward; exact per-horizon cache lifetime is unchanged.

- [x] RED: compare all path metrics to original forward-derived positions; cover identical endpoints, interpolation rounding and boundary clearance/corridor values.
- [x] Compute required positions in a native batch, omitting unused quaternion/Pose creation; do not replace the true end with the fraction1 interpolation.
- [x] GREEN: all full receipts/path/score/error documents exact; separate timing.

## Task 5: installed validation and acceptance

- [x] Freeze scoped source/hash snapshot; normal private colcon builds on Mac and ai-station; verify native/module/URDF/resource origins.
- [x] Directed tests and complete ordinary so101_demo_py/test xdist gate, workers=min(8,logical CPUs), logs/JUnit/skip/worker proofs. No perception benchmark suite. Mac uses fixed ROS Python; Linux scratch follows registered retention contract without a second evidence root.
- [x] Repeat 64 frozen solver cases on each tested platform, recording lossless lhs/rhs/steps and exact outcomes.
- [x] Formal isolated ai-station B/O run using original unchanged timer, balanced order, 15 samples per fixture/variant. Verify outputs, single-thread affinity, sibling idle, zero migrations and restoration.
- [x] Ratio0.3948036895 <=0.50 and median207.5054745ms <=259.632309ms; no further optimization required for this goal.
- [x] Inline review compatibility, source/install provenance, generated C reproduction, scoped diff and retention inventory.
- [ ] Publish current Gitee branch under persistent user authorization after required gates pass.
- [x] Update ledger/checkpoint and report retained/archived/deletion candidates.
- [ ] Mark native goal complete after publication; all measured objective gates achieved.

## Final result and execution notes

Formal ai-station median525.59152825 ->207.5054745ms (-60.519631%). Mac ordinary xdist8:3928passed30skipped; Linux directed42passed. Independent64case6043update traces match on each platform; full four-fixture workload18566updates match. Complete evidence transfer checked. The Linux system benchmark interpreter lacks xdist/mujoco; full Linux ordinary package qualification was not run and shared dependencies were not modified. The complete ordinary package gate ran on the fixed Mac ROS runtime.

The matrix workspace optimization additionally calls NumPy own versioned float64 matmul capsule for released1.26.x/2.4.x; other versions/layouts fall back to normal NumPy dispatch. This preserves original arithmetic and was accepted by the same exact differential and installed gates.

Final acceptance evidence: sole registered root/loop50/{result.md,summary.json,review/final-verification.json,transfer-proof.json}; publication and native goal status:loop50/publish.json.
