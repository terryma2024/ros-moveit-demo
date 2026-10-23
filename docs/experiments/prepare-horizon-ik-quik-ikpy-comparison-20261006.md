# SO-101 QuIK / IKPy comparison — 2026-10-06

The experiments do not support replacing the current solver with either tested
library configuration. QuIK reduces individual solve latency substantially but
loses a supported complete horizon. Weighted IKPy retains the two supported
horizon outcomes and improves acceptance on the adversarial request set, while
increasing latency. Production code and dependencies were unchanged.

This is a headless compute experiment. It establishes no robot execution,
controller, physics, collision-scene or live-placement result.

| Frozen implementation | Method and model | Integration and constraints |
| --- | --- | --- |
| Current bb9a9c5a045410d62d25bd76380ae5401cdee76c | Native Cython loop, finite-difference Jacobian, damped least squares; canonical URDF | Current residual, clipping with joint margin, exact horizon cache and native path sampling |
| QuIK a9ebd1f21dfd3c9f0869140dfb0a4ae5a538cccc | C++ / Eigen, analytic Jacobian and Hessian product, Halley iteration; standard DH | Fixed-size DOF=5 C ABI adapter; upstream lacks joint-limit enforcement; GNU AGPL v3 |
| IKPy 4.1.0 e76c285c06121b2c7c71fc7541a1a9e571b03873 | Python / SciPy least_squares, SymPy-generated FK; URDF | Active joint bounds; full-frame matrix residual; Apache 2.0; NumPy backend tested |

Primary research sources: [QuIK](https://github.com/steffanlloyd/quik),
[QuIK solver source](https://github.com/steffanlloyd/quik/blob/a9ebd1f21dfd3c9f0869140dfb0a4ae5a538cccc/include/quik/IKSolver.hpp)
and [IKPy](https://github.com/Phylliade/ikpy). The frozen IKPy source also offers
JAX. That optional backend was absent and was not installed or measured;
the conclusions concern NumPy/SciPy mode.

All artifacts use the sole registered root:
`/opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/solver-compare-01`.
The remote `/data/tmp/so101-prepare-horizon-ik-20261004-01a10735-solvercmp-01`
is task-owned execution staging, completely copied into the registered root.

**Controls.** Both external models passed 2,003 FK checks: home, control
bounds and 2,000 frozen random joint vectors. Maximum matrix coefficient
differences were 4.330e-15 for QuIK and 1.110e-15 for IKPy, below the unchanged
1e-12 gate. IKPy retains the exact canonical URDF chain; QuIK uses an audited
five-row DH conversion. Stable rank/common-normal calculations avoid amplifying
axes parallel to floating-point roundoff. Robot geometry and gates were not
relaxed.

Platform: ai-station, Intel i9-13900HX, Python 3.12.3, NumPy 1.26.4,
SciPy 1.11.4, SymPy 1.12, Eigen 3.4.0-4build0.1 and GCC 13.3.0. CPU14 and
SMT15 form the eighth P core, ordinal 7; Linux core_id is 28. A temporary
cgroup v2 isolated partition reserved both, with computation pinned to CPU14.
All 25 measured processes had one computational thread, zero migrations
during the measured window and zero SMT15 user/nice/system tick changes.
Existing powersave policy remained unchanged; frequency and temperature were
recorded. CPU masks were restored. Existing checkouts, submodules and tmux
were preserved.

Each backend ran in five fresh processes, occupying each execution-order
position once. Each process had one warmup and three timed repetitions per
request and fixture: 15 observations per input. Pilot data is excluded.
p95 uses NumPy linear interpolation.

The 64 frozen requests include 48 far-seed reachable targets, home/limit/sign
and strict tolerance-boundary probes, an unreachable integer target and four
input-validation probes. The latter remain separately recorded; 60 finite
requests enter the main table. This adversarial suite is not field reliability.
Default gates are 2 mm and 0.10 rad; frozen per-case overrides are preserved.

Foreign adapters check clipped seeds and validate returned candidates using
canonical FK, finite coordinates and the 0.002 rad control joint margin.
QuIK outputs may be shifted by equivalent 2*pi representatives within bounds,
closest to the seed. Solved angles are never clipped into acceptance.
IK timing includes conversion and gates. Horizon timing includes the unchanged
planner, exact per-horizon cache, search, scoring, path samples and receipts.
Construction/imports and external serialization are excluded. Foreign paths
use existing generic validation; current retains its native sampling route.

| Configuration | IK median, ms | IK p95, ms | Accepted / 60 | Retained current successes / 34 |
| --- | ---: | ---: | ---: | ---: |
| Current native | 1.246 | 6.582 | 34 | 34 |
| QuIK actual defaults | 0.148 | 0.176 | 37 | 27 |
| QuIK damped | 0.149 | 0.253 | 36 | 27 |
| IKPy stock NumPy | 6.584 | 11.287 | 38 | 33 |
| IKPy weighted NumPy | 5.672 | 15.232 | 42 | 33 |

For requests accepted by both, the median per-request latency ratio against
current was 0.249 / 0.245 / 6.152 / 5.659 for the four alternatives above.
QuIK's algorithm-call median including C ABI/buffer handling but excluding
adapter pose gates was approximately 0.019 ms. That ancillary value is not
the complete interface latency.

QuIK README and constructor defaults differ. Actual defaults use 100
iterations, zero damping and gradient-failure budgets 5/20. The explicitly
damped case uses 200 iterations, lambda_squared=1e-10, budgets 20/80,
1e-12 exit norm and automatic linear step limit. IKPy uses full-frame
orientation and max_nfev=200 with its default optimizer tolerances; this
budget is not equivalent to 200 outer iterations. Weighted IKPy uses
ORIENTATION_COEFF=0.08/sqrt(2), a small-angle scaling toward current's
0.08 axis-angle weight. The finite-rotation residual remains different.
All settings preceded formal measurement.

With five joints, QuIK's undamped 6x6 A*A.transpose() has rank at most five,
so its LLT solve lacks a positive-definite guarantee. This is an inference
from the frozen linear algebra, not a claim that every invocation failed.
Actual default outputs were stable on this machine and remain retained.

| Backend | p18_home | canonical_home | outer_boundary | unreachable |
| --- | --- | --- | --- | --- |
| Current | 396.0 ms, 14 steps | 139.6 ms, 14 steps | 190.2 ms, rejected | 89.3 ms, rejected |
| QuIK defaults | 72.6 ms, incomplete | 203.4 ms, 14 steps | 27.4 ms, rejected | 2.4 ms, rejected |
| QuIK damped | 2.4 ms, incomplete | 102.0 ms, 14 steps | 2.5 ms, rejected | 2.4 ms, rejected |
| IKPy stock | 52.1 ms, incomplete | 1130.3 ms, 14 steps | 53.6 ms, rejected | 53.9 ms, rejected |
| IKPy weighted | 1554.3 ms, 14 steps | 1098.6 ms, 14 steps | 436.7 ms, rejected | 56.3 ms, rejected |

The four-fixture suite median was 203.838 ms for current and 786.994 ms for
weighted IKPy, a factor of 3.86. QuIK suite times include loss of the supported
p18 path and cannot establish successful horizon acceleration. Every current
full document was byte-identical to the preceding EXP-031 Linux measurement.
Foreign joint vectors, branch choices and scores changed. Nine shared accepted
requests had identical joint-vector bits from the shared seed gate; no
equivalence to the preceding native optimizations is claimed.

An untimed replay of p18's first target and all 14 identical seeds explains
the first rejection for damped QuIK and stock IKPy. Both returned in-limit
candidates with small orientation error, but position error was approximately
4.625 mm and 4.873 mm respectively, exceeding 2 mm for every seed. Weighted
IKPy reached approximately 0.274 mm and 0.01446 rad and accepted all 14.
Current also accepted all 14. Default QuIK accepted 13 at this first target,
with one bounds rejection; its complete horizon failed later. This supports
a residual/constraint compatibility issue for the damped and stock variants;
it does not establish a one-parameter repair.

**Verification and limits.** Every timed call matched its warmup output,
and results matched across five processes. Every selected step passed the
recorded pose/control-limit gates. External numerical modules were unmodified.
IKPy's import analytics HTTP call was disabled and its daemon joined before
timing. Incremental backend initialization after common reference creation was
about 1.2 ms for QuIK and 267 ms for IKPy; these are not full cold-process
startup measurements.

The explicitly required repository perception benchmark_test gate ran through
colcon with xdist8: 585 tests, 553 passed, 32 failed, no errors/skips.
All failures stem from CONFIG_SHA256_MISMATCH: YAML SHA5c8b0046... differs from
CLI constant511e0e64.... Both files are byte-identical to frozen baseline
7a62d8e8, current source and private installation. This pre-existing unrelated
issue was retained without product edits. It prevents claiming the repository
benchmark gate passed; the separate IK experiment remains valid.
Ordinary package tests were not rerun because production code was unchanged.

Further latency research should retain the current task residual, limits and
acceptance policy while examining analytic derivatives and a bounded native
solve loop. QuIK demonstrates the computational opportunity. Direct adoption
would change numerical/task behavior and needs a separate reviewed
implementation plan and outcome/equivalence contract.

Audit artifacts in the registered phase:

- Frozen protocol-formal-01.json; compare_model.py; quik_shim.cpp; prepare.py;
  geometry_gate.py; run_compare.py; isolate_and_run.py; analyze.py.
- analysis.json; comparison.png / comparison.svg; complete raw outputs,
  perf counters and process proofs in remote-staging/formal-01.
- First-boundary replay in remote-staging/diagnostic-01.
- package-benchmark-gate: JUnit, logs and baseline root-cause proof.
- remote-inventory.json: 660 files, 121,152,175 bytes, zero symlinks;
  every SHA256/size verified after transfer; prior inventory also retained.

Retained: all pilot/formal/diagnostic and invalid setup evidence. Archived:
none. Deleted: none. Private staging, duplicate source/build trees and scratch
are deletion candidates only, listed in solver-compare-01/retention.json.
