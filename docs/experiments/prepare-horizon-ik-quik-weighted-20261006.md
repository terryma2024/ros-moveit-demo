# Weighted QuIK position-gate experiment, 2026-10-06

Weighting restored the first p18 target's position gate while keeping solve latency near the original QuIK result. It did not restore the complete supported p18 horizon: weights 0.08, 0.04 and 0.02 all stopped at the sixth MOVE_ABOVE_OBJECT waypoint. The current production solver is unchanged.

This is the user-approved weighting experiment. IKPy was excluded. Tests and timing ran on ai-station; artifacts are retained under the sole registered evidence root:

`/opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735`

Current numerical source remains bb9a9c5a. QuIK is frozen at a9ebd1f21dfd3c9f0869140dfb0a4ae5a538cccc. The task-owned C++ copy applies W = diag(1,1,1,w,w,w) to the residual and matrix rows in both Halley linear solves, and uses the corresponding weighted progress norm. Hessian construction retains the original geometric Jacobian. Damping 1e-10, 200 iterations, gradient-failure budgets, clamps and final independent pose/control gates were unchanged. Five-by-five solving, split tolerance stopping, joint-step caps and bound-aware iteration were not added.

Weights were bounded to three trials: the current residual scale 0.08, its half 0.04, and 0.02, the default position/orientation tolerance ratio. Parameters were frozen before formal measurement. The original library, each weighted library, source hashes, patch and build commands remain available.

The original regression failed with 14 position assertions and no test errors. Weight 0.08 then passed the same test. A final run checked all 14 original seeds for every weight on the isolated core. Each returned solution passed the original 2 mm position, 0.10 rad orientation and 0.002 rad control-margin gates.

| QuIK orientation weight | First-target position error, mm | Orientation error, rad | Accepted seeds |
| --- | ---: | ---: | ---: |
| 1 | 4.624560 | 0.00155950 | 0/14 |
| 0.08 | 0.274384 | 0.01445883 | 14/14 |
| 0.04 | 0.071451 | 0.01506056 | 14/14 |
| 0.02 | 0.018050 | 0.01521890 | 14/14 |

The 14-seed spread was below 0.000004 mm in every row; the table rounds its midpoint. All four QuIK libraries passed the same 2,003 canonical FK vectors, including home, control bounds and 2,000 frozen random vectors. Maximum matrix difference was 4.3298697960381105e-15, below the 1e-12 gate.

Formal timing used CPU14, on P-core ordinal 7 (the eighth P core), Linux core_id 28. Sibling CPU15 was reserved idle. A temporary isolated cgroup excluded both threads from other userspace work; each measured process used one computational thread. All 25 process proofs show zero measured migrations and zero CPU15 user/nice/system tick changes. Original cpuset state, powersave governor, both existing checkouts/submodules and claude tmux were preserved.

Each backend occupied each of five process-order positions once across five fresh processes. Each process ran separate warmups and three timed repetitions per request and fixture: 15 observations per input. The same frozen 64 requests include 60 finite probes and four separately recorded input-validation cases. Pilot data is excluded. Median and NumPy-linear p95 are reported.

Solve timing includes adapter conversion, the clipped-seed gate, the native solve and the final canonical FK gate. Full-horizon timing includes the unchanged search, cache, scoring, path samples and receipts. Construction and external evidence serialization are outside warm timing. Backend solutions, branch choices and receipts differ; no bitwise equivalence is claimed.

| Backend | Solve median, ms | Solve p95, ms | Accepted finite requests | Retained current successes | Canonical horizon median, ms | Canonical p95, ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Current native | 1.246972 | 6.596753 | 34/60 | 34/34 | 138.893 | 141.917 |
| QuIK, weight 1 | 0.148230 | 0.252307 | 36/60 | 27/34 | 101.312 | 107.476 |
| QuIK, weight 0.08 | 0.149282 | 0.256537 | 37/60 | 30/34 | 102.504 | 107.486 |
| QuIK, weight 0.04 | 0.151538 | 0.257960 | 40/60 | 30/34 | 103.308 | 109.436 |
| QuIK, weight 0.02 | 0.150207 | 0.254707 | 40/60 | 29/34 | 103.073 | 109.272 |

All canonical horizons contained 14 steps. Weight 0.08 took 102.504 ms versus current 138.893 ms, a ratio of 0.738. Its median per-request latency ratio on the 30 requests accepted by both was 0.240. The intersection accepted by all five backends contains 25 requests; per-backend ratios for that common mask are retained in analysis.json. Mixed success/failure solve medians in the table are characterization data, not a successful full-suite speedup. The adversarial request set is not a field reliability estimate.

Weight 0.08 retained 30 of the current 34 finite successes, up from original QuIK's 27. The remaining four losses are random_10, random_18, random_29 and random_39; every returned candidate violated control bounds, and random_10 also failed position. Weight 0.04 retained the same 30, while 0.02 retained 29. The four input-contract probes and their exception differences are preserved separately; weight 0.08 recovered positive_inf_seed after canonical seed clipping, while 0.04/0.02 still rejected it. Foreign NaN exception behavior differs from current.

All weighted p18 runs accepted waypoints 1 through 5, then rejected all 15 actual seed calls at waypoint 6. No complete prepared path was published. The unchanged current path completed 14 steps. Failed p18 return times are retained in raw data and excluded from successful-horizon speedup claims. All variants rejected outer_boundary and unreachable.

An untimed replay on the same isolated P core classified waypoint 6: all 15 candidates per weight failed position; 8/11/10 also violated bounds for weights 0.08/0.04/0.02. Minimum position errors were 2.545/2.515/2.631 mm. The current accepted solution at this target had 0.980 mm position error, 0.02929 rad orientation error and wrist q=1.65606 at the upper control boundary. Thus a solution satisfying the existing gates exists; the QuIK rejection does not establish target infeasibility. Weighting alone did not reproduce the current solver's controlled iteration behavior.

Next work should test native step control, control-bound-aware updates and task-tolerance stopping as separate variables. Remaining position failures also occur for in-bounds candidates, so limits alone are not a complete diagnosis. Those changes were outside this weighting-only trial.

The required repository benchmark gate ran through colcon with the fixed Mac ROS Python and xdist8: 585 tests, 553 passed, 32 failed, zero errors/skips. Twenty-nine failures directly report CONFIG_SHA256_MISMATCH; three dry-run tests fail on the resulting exit code. YAML and CLI hashes are unchanged from the original frozen 7a62d8e8 baseline, matching the previous comparison gate. An earlier sandbox run failed before collection because pytest_rerunfailures could not bind a localhost socket; that invalid run is retained separately. No all-tests-pass claim is made. Ordinary package tests were not rerun because production code was unchanged.

This was pure computation. No ROS stack, simulator, GUI or physical robot ran. Original/current outputs were byte-identical to EXP-036 in all five processes. Weighted outputs matched their warmups and across all five processes. Every selected step passed independent recorded pose and joint-margin checks.

Artifacts in quik-position-01/weighted-01 include analysis.json, weighted-core.patch, both weighted include trees, build scripts, test_first_position_gate.py, frozen protocols, complete remote-staging results, package-gate evidence and inline-review-final.json. The remote copy contains 455 files and 17,274,957 bytes, with no symlinks; all recorded hashes and sizes were verified after transfer.

Retained: all trial, formal, diagnostic, source/build and package-gate evidence. Archived: none. Deleted: none. Remote staging, duplicate binaries and package-test scratch are deletion candidates only; no deletion was authorized.
