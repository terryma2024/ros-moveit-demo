# Twenty-point current / weighted QuIK comparison, 2026-10-06

The current native solver completed all 20 frozen task points. QuIK with orientation weight 0.08 completed 18; P18 and P19 failed at the final MOVE_ABOVE_OBJECT waypoint. On the 18 points completed by both, median warm IK-prefix latency fell from 151.914 ms to 111.752 ms, a 26.4% reduction. The weighted QuIK version does not retain all current-supported points and was not adopted into production.

This is the user-requested comparison of the existing native solver and the frozen weighted QuIK candidate. Only the measurement inputs changed. The authoritative catalog is `src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml`: four anchors and sixteen samples, mapped in source order to P01 through P20. Its SHA256 is `c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5`; its bytes match the original frozen 7a62d8e8 source baseline. P18 is `sample_14_far_right`, the earlier p18 fixture.

Each point starts from the same frozen home arm angles (five zeros), with gripper q=0.465038. Both use the same URDF, world/TCP transforms, targets, 14 waypoints, beam width 3, seed generation, candidate order, scoring, path sampling and horizon-local cache policy. Backend solutions, deduplication and receipt counts may differ. Position tolerance remains 2 mm, orientation tolerance 0.10 rad and control-limit margin 0.002 rad. No weight, damping, iteration, stopping or bound-handling parameter was retuned.

The current numerical source remains bb9a9c5a. The source is the task-owned optimized Mac/source lineage; Linux runs that frozen build. The Linux native module SHA256 is `196ce025339b1b3248fa3b84e11de8af60b3159b096cd501d0dcbb95eb714057`. Weighted QuIK uses the unchanged library `74523747023cf4cef7de881a028ac79c6ac7ae964c35bce2a879a02c21fa9a37` and weighted header `dc63f92ec9642b44202448c384f7c1a1f7d64124ecd4d37686406f56e5d5656c`. The Python adapters and measurement runner are byte-identical to EXP-042. The previous 64 individual IK requests were not retimed in this phase.

Timing ran on ai-station with CPython 3.12.3 and NumPy 1.26.4. CPU14 belongs to the eighth P core (ordinal 7, Linux core_id 28); sibling CPU15 was reserved idle. Six fresh processes per backend alternated in three A/B and three B/A pairs. Each process had separate warmups and three timed repetitions per point: 18 observations per point and backend, 720 timed horizons in total. Point order rotates during timed repeats. One computational thread and BLAS/OMP thread limits of 1 were enforced. All 12 before/after proofs show no measured migrations or CPU15 user/nice/system tick changes. The original cpuset and powersave governor were restored; old checkouts, submodules and claude tmux were unchanged.

The timer surrounds the real `prepare_horizon` call, including search, FK scoring, cache allocation and receipt construction. Model/library creation and evidence serialization are outside warm timing; initialization is recorded separately in raw warmup metadata. No ROS waiting, simulator, controller, perception or physical grasp ran. Passing means that a complete 14-waypoint IK prefix was generated, not that a cup was physically grasped or placed.

| Metric | Current native | QuIK, weight 0.08 |
| --- | ---: | ---: |
| Complete points | 20/20 | 18/20 |
| Shared-success latency samples | 324 | 324 |
| Shared-success pooled median, ms | 151.914 | 111.752 |
| Shared-success pooled p95, ms | 168.432 | 132.671 |
| Mean of the 18 point medians, ms | 151.714 | 111.664 |

The shared-success pooled median ratio is 0.735628; the ratio of equally weighted point medians is 0.736019. Each shared point contributes 18 observations. Neither failed QuIK exit is counted as a successful speedup. p95 uses NumPy linear interpolation. These fixed-catalog outcomes do not estimate physical grasp reliability.

| Point | Catalog ID | Current median / p95, ms | QuIK median / p95, ms | QuIK result |
| --- | --- | ---: | ---: | --- |
| P01 | task_start | 149.289 / 173.614 | 108.844 / 137.699 | 14 steps |
| P02 | cup_test_forward_5cm | 154.448 / 176.090 | 112.471 / 128.710 | 14 steps |
| P03 | cup_test_left_5cm | 146.934 / 170.085 | 112.239 / 127.483 | 14 steps |
| P04 | cup_test_right_5cm | 148.021 / 160.269 | 112.745 / 126.860 | 14 steps |
| P05 | sample_01_near_left | 150.576 / 161.686 | 116.126 / 134.242 | 14 steps |
| P06 | sample_02_near_center | 151.405 / 161.800 | 110.741 / 132.005 | 14 steps |
| P07 | sample_03_near_right | 154.918 / 162.788 | 121.897 / 126.564 | 14 steps |
| P08 | sample_04_near_left | 154.161 / 165.343 | 109.224 / 121.182 | 14 steps |
| P09 | sample_05_near_center | 155.700 / 164.212 | 109.007 / 121.763 | 14 steps |
| P10 | sample_06_mid_left | 149.865 / 166.822 | 110.297 / 138.890 | 14 steps |
| P11 | sample_07_mid_center | 149.986 / 163.235 | 113.612 / 133.307 | 14 steps |
| P12 | sample_08_mid_right | 150.321 / 166.352 | 109.699 / 132.118 | 14 steps |
| P13 | sample_09_mid_left | 152.858 / 165.510 | 113.412 / 127.576 | 14 steps |
| P14 | sample_10_mid_center | 149.690 / 157.939 | 108.983 / 138.229 | 14 steps |
| P15 | sample_11_mid_right | 148.931 / 164.048 | 116.554 / 132.935 | 14 steps |
| P16 | sample_12_far_left | 156.575 / 166.948 | 106.112 / 129.321 | 14 steps |
| P17 | sample_13_far_center | 149.658 / 167.384 | 108.687 / 136.604 | 14 steps |
| P18 | sample_14_far_right | 415.752 / 423.760 | 42.820 / 54.006 | Rejected at MOVE_ABOVE_OBJECT / 6; time is rejection latency |
| P19 | sample_15_far_center | 376.597 / 388.558 | 43.601 / 50.029 | Rejected at MOVE_ABOVE_OBJECT / 6; time is rejection latency |
| P20 | sample_16_far_right | 157.513 / 188.691 | 109.307 / 120.260 | 14 steps |

Every current row contains 14 selected steps. Weighted QuIK contains 14 steps for P01 through P17 and P20; P18 and P19 contain no complete selected path. Both failures rejected all 15 candidate seed calls at approach waypoint 6. P18 cup position is [0.051023, -0.339445, 0.165] m; P19 is [0.008183, -0.339434, 0.165] m. The failure receipts retain the final gate rejection. This phase did not replay every rejected joint vector to separate position, orientation and bound causes for P19.

All selected waypoints passed the recorded independent canonical FK pose/control gates. Current maximum selected position error was 1.420810 mm and orientation error 0.086101 rad, with minimum joint margin 0.002 rad. On its 18 complete points, QuIK maxima were 1.434305 mm and 0.085715 rad, with minimum margin 0.055014 rad. Those maxima cover different success sets. Outputs matched warmups, timed repetitions and all six fresh processes per backend; P01 and P18 output documents were byte-identical to the previous canonical/p18 experiment for both backends.

The required Mac repository benchmark gate used the fixed ROS Python, task-private installed overlay, colcon and xdist8. It collected 585 tests: 553 passed, 32 failed, zero errors/skips. All 32 failing test IDs match the previous gate: 29 direct CONFIG_SHA256_MISMATCH failures and three resulting dry-run exit-code failures. No new failing test ID appeared. This remains a failing package gate; no all-tests-pass claim is made. Ordinary package tests were not rerun because product source was unchanged.

The sole registered evidence root remains `/opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735`. This phase is `quik-position-01/points20-01`. It retains the catalog, frozen protocol, source/binary hashes, all raw output documents and timing samples, analysis.json, points20.csv, points20-latency.png, CPU restoration proofs, package-gate results and inline review. The complete remote transfer contains 355 files and 62,227,284 bytes, plus its inventory; every file size and SHA256 was verified. The first preflight used an incorrect `.py` path for the native module; it failed before measurement, was corrected from the existing installed-SO provenance, and remains recorded separately.

Retained: all phase evidence and earlier runs. Archived: none. Deleted: none. Remote task staging, duplicate source/binary copies and package-test scratch remain deletion candidates only; deletion was not authorized.
