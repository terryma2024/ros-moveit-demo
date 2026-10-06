# Selectable native and QuIK pose IK

Both solvers now use the same factory and pose IK interface. `native` remains the
default. The dynamic pick-place and reachability CLIs accept `--ik-backend native`
or `--ik-backend quik`; an explicit argument overrides `SO101_IK_BACKEND`.
Reachability preflight and execution resolve the same selection, and the Mac
launcher and parallel worker environment retain it.

QuIK is an optional compiled module. Build with `SO101_BUILD_QUIK=1` and Eigen
3.4.0 to install both kernels. A native-only build does not require Eigen. Selecting
QuIK without its module raises `QUIK_BACKEND_UNAVAILABLE`. See the
[build and API guide](../guides/so101-ik-backend-selection.md).

The QuIK adapter retains the measured orientation weight of 0.08 and the frozen
200-iteration solver parameters. Both solvers expose `solve`, `forward`,
`forward_positions`, `joint_limits` and `orientation_error_rad`. QuIK checks
solutions with the project's canonical FK and original tolerances: 2 mm position,
0.10 rad orientation and 0.002 rad joint-limit margin. It normalizes whole-turn
equivalent angles and uses no native IK fallback.

## Installed twenty-point comparison

The task-private Linux installation was built from base commit
`ed7998674d44b5ee8e37594ea94b839de5242fe1` plus the approved integration diff.
Its source archive SHA256 is
`e00d51115bf4d2b0c675c7f5b89ad3f08796f8e0808448767c6e9588f6650492`.
The actual installed Python and native artifacts were fingerprinted before and
after each process. Existing ai-station checkouts were preserved.

The comparison used the same frozen twenty-point catalog, start states, targets
and full fourteen-waypoint IK prefix as [EXP-044](prepare-horizon-ik-quik-points20-20261006.md).
Each backend ran in six fresh processes, with three timed repetitions per point:
720 measured prefixes in total. The order balanced three native/QuIK and three
QuIK/native pairs, with rotated point order. Warmups and construction were outside
the timed boundary. Cold setup measurements do not support a startup comparison:
the harness reused a preconstructed reference for native.

Every process used isolated P-core CPU14 with SMT sibling CPU15 idle, one compute
thread and BLAS/OMP thread limits of one. Recorded migrations and sibling
user/nice/system ticks were zero. CPU isolation was restored afterward; governors,
existing checkouts, submodules and tmux state matched their prior values.

| Result | Native | QuIK, weight 0.08 |
| --- | ---: | ---: |
| Complete IK prefixes | 20/20 | 18/20 |
| Shared-success samples | 324 | 324 |
| Shared-success pooled median | 147.225650 ms | 103.091704 ms |
| Shared-success pooled p95 | 156.056326 ms | 112.767584 ms |

QuIK's median was 29.98% lower on the common eighteen successful points, P01–P17
and P20. Failed-prefix times are excluded from that comparison. P18 and P19 still
reject all fifteen candidates at `MOVE_ABOVE_OBJECT` waypoint 6. Keeping QuIK as an
explicit option preserves this known limitation; these results do not establish
physical grasp or ROS/MoveIt execution success.

All twenty native output documents matched EXP-044 exactly, including joint
vectors, selected steps, scores, pose errors and receipt order. All twenty QuIK
documents also matched after the one planned receipt-code change:
`COMPARISON_GATE_REJECTED` becomes `DYNAMIC_IK_RESIDUAL_EXCEEDED`. Outputs remained
identical across the six fresh processes for each backend.

An untimed audit of the installed modules checked 2,003 FK vectors. The largest
QuIK-versus-canonical matrix difference was `4.33e-15`, below the `1e-12` threshold.
Independent recalculation of all 532 selected-step pose and joint-margin metrics
matched the recorded values exactly. Replaying the frozen 64 requests per backend
preserved every return/reject decision and returned joint vector; accepted pose
metrics were exact. Native error classes and messages were also unchanged.

## Package verification

The Mac private installation passed the complete ordinary `so101_demo_py/test/`
gate with fixed ROS Python, NumPy 2.4.6 and eight xdist workers: **3,953 passed,
30 skipped, no failures or errors**. The QuIK integration tests ran with the
compiled module required. A separate native-only build succeeded with an absent
Eigen path and confirmed the explicit missing-QuIK error.

The separate `benchmark_test/` gate collected 585 tests: 553 passed and 32 failed.
The failed test identities exactly match the previous gate: 29 existing
`CONFIG_SHA256_MISMATCH` failures and three related dry-run failures. That gate
remains failed; the integration added no failing test identity.

Initial invalid executions are retained separately: a sandbox-blocked pytest
plugin could not run the intended assertions, and an incomplete private Git and
symlink snapshot caused unrelated ordinary test failures. After restoring the
actual frozen source closure, the full ordinary gate passed without changing its
scope or worker count.

## Evidence and retention

All artifacts belong to the existing registered root:
`/opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735`.
The `dual-backend-01/` phase retains the approved protocol, RED/GREEN results,
private builds, JUnit, source archive, raw measurements, installation provenance,
numerical audits and inline review. Its remote archive copy verified 3,576 regular
files and 49 symlinks by size, SHA256 or link target.

No runs were archived or deleted. Task scratch, remote staging, private build
duplicates and transfer archives are deletion candidates only. EXP-046/047 and
CP-025 in the [task ledger](prepare-horizon-ik-20261004-01a10735-experiment-ledger.md)
record the final readback; publication hashes are retained in
`dual-backend-01/publish.json`.
