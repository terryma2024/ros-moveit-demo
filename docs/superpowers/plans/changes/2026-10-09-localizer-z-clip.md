# Localizer z-clip (R-b): the landing ring never enters the circle fit

Date: 2026-10-09 (ledger CP-3479). Findings: `handoffs/.../perception-risks-20261009/` (`findings.md`, `ring_fix_eval.json`, `ring_fix_summary.txt`, `tools/`).

## Change

`application/object_pose.py`: `RgbdLocalizer.localize` drops the world points with z < `CUP_FIT_MINIMUM_Z_M` (0.135 m) before `estimate_upright_cup_pose`, right after the camera-to-world transform and before the circle fit. The constant is named and carries its rationale: the red landing ring lies flat on the table at z about 0.1201 (table top 0.12 m); the segmentation mask of a cup near it bleeds onto the ring, which pulled the fitted centre by up to 4.8 mm; the cup wall starts at the table top, so only the cup's lowest 15 mm is cut (0.075 m of the 0.09 m remain). It is a constructor parameter (`fit_minimum_z_m`, finite). After the clip `GEOMETRY_REJECTED` is raised when fewer than `minimum_cup_points` remain (a candidate that is only ring or table). `LocalizedObject.points_world` and `valid_depth_point_count` are the points the fit used (clipped, read-only as before). R6's z-extent test now sees the cup's remaining 0.075 m (threshold 0.05 m), a flat ring candidate has no points left.

## Evidence

Rendered ACT-scene gate (production detector with the BGR fix, Broker wire conversion, `BrokerMaskLocalizer` + R6 + clip), now **487 cases**: 3 anchors, 300 random, 40 near the ring, and the new **dense ring stratum** (12 distances 0-0.12 m from the ring centre x 12 azimuths, the investigator's `render_dense.py` geometry; `act-scene-gate-q1.json`).

| | before (343 cases) | with the clip (487 cases) |
| --- | --- | --- |
| exactly one cup | 343 of 343 | 486 of 487 (99.8%) |
| wrong object | 0 | 0 |
| xy error mean / p95 / max | 0.555 / 0.838 / 4.81 mm | 0.480 / 0.552 / 1.393 mm |
| dense ring (144) mean / p95 / max | 0.75 / 2.06 / 4.09 mm (findings, unclipped) | 0.470 / 0.530 / 0.917 mm |
| 1 px mask sensitivity p95 (anchor / random / dense ring / ring) | 0.032 / 0.549 / n.a. / 1.309 mm | 0.023 / 0.025 / 0.035 / 0.051 mm |

Gates: exactly-one >= 99%, 0 wrong object, overall p95 < 1.5 mm, mask sensitivity p95 <= 1.0 mm (anchor, random), **dense ring p95 <= 1.0 mm (new)**. The clip also removes the mask-boundary sensitivity almost completely.

**Saved broker inputs:** 147 inputs now exist (125 before). The corrected detector gives 2 candidates on every one; R6 leaves exactly one on 147 of 147. For the 125 compared with the unclipped check the pose changes by 0.006-0.007 mm (they are cups at the anchor, away from the ring); distance from the default-anchor ground truth stays 0.475 mm (`saved_check_clip.json`, `saved_check_clip-compare.txt`).

## The 1.39 mm residual (`ring03`; investigated)

`ring03` puts the cup 96 mm from the ring centre, its wall touching the ring's outer edge (outer radius about 55 mm + cup 40 mm). Clipped, the error is 1.39 mm (unclipped 1.19 mm); `dense_d090_a02` (0.92 mm) is the same situation. `residual_probe.py` on `ring03`: after the clip 35 points of the fit still lie over the ring's footprint (legitimate cup wall), the fitted radius is 0.0405 m against 0.040 and the azimuth span is the full circle; **eroding the mask by 2 px brings the error to 0.34 mm (radius 0.0396), dilating by 2 px takes it to 4.6 mm**. With the ground-truth mask the same case gives 0.55 mm. So the residual is the YOLO mask boundary at a depth discontinuity (silhouette pixels with depth of the cup's edge or the table behind it), not the ring's height: a z-clip cannot remove it, and the clip is slightly worse than nothing here only because cutting the lowest 15 mm removes wall points that diluted the boundary error. It stays below the 1.5 mm gate and the p95 of that stratum is 0.55 mm. Not fixed (more erosion in the detector trades against the other strata); the dense ring stratum would catch a regression.

## Known case outside the formal domain

`dense_d030_a07` (cup 30 mm from the ring centre) gives two candidates that both pass R6 (the cup at 0.963 and a 0.336 fragment that also localizes as a cup): `BROKER_CANDIDATE_AMBIGUOUS: 2 of 2`. It was already two survivors before the clip. It lies inside the 0.065 m disc around the ring centre that the findings propose to exclude from formal starts (R-a), so the formal-collection domain never contains it; it is counted in the overall exactly-one figure (486/487) and not hidden.

## Tests (RED first)

`test_rgbd_localizer.py`: the constant lies between the ring and the cup wall; ring points added to the cup cloud do not move the fit (the same cloud without the clip is displaced by more than 1 mm or refused); a candidate that is only ring/table is `GEOMETRY_REJECTED`; the parameter is checked; the existing exact-geometry test's cloud now starts above the clip (z 0.14). RED against CP-3478: 4 failures. The ACT-scene gate gained the dense stratum, its per-stratum error statistics and gate.
