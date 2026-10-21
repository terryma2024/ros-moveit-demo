# SO-101 ACT: Teacher success boundary and uniform scene sampling — design and plan

Status: CONFIRMED by the human on 2026-10-20 ("中心的ok。可以按上面来。"), with Q1–Q6 as recommended. Queued: it runs after to-do items 18 (shorter Teacher dwells) and 19 (phase-1 recording throughput), which the human wants first ("在此之前，我希望能先执行…"), so the boundary is measured with the final Teacher policy.

## Why (human, 2026-10-20)

"从这图看，现在的训练数据采样点分布有问题。我需要一个更合理的采样点：首先需要尝试得到Teacher Expert策略能成功抓取的边界（不用很精确，找到米字形8个点就可以），然后在这个边界内，相对均匀的采样。"

The 103 formal scenes (EXP-625) all lie in a triangle of about 7 × 6 cm (x −0.049…0.020, y −0.341…−0.280); see
`REG/act-dataset-side-wrist-103-20261019/plots/initial-positions.png`. The standard rollout points sit on its edges or outside it:
right_5cm is 51 mm from the nearest training scene, and it fails in every rollout.

## Step 1: the Teacher success boundary along 8 rays

- **Centre:** C = (0.02, −0.29), between task_start and forward_5cm. It sits inside the current data and near the arm's reset-pose gripper position.
- **Rays:** 8 directions, 45° apart (E, NE, N, NW, W, SW, S, SE in world x/y).
- **Hard limits:** each ray stops before any of these:
  - the table edge, keeping the 0.04 m cup radius plus a 0.01 m margin on the table;
  - the pedestal;
  - the place-target exclusion zone (cup centre at least 0.060 m from the target (−0.08, −0.25), as in the formal sampler).
- **Search per ray:**
  1. **Offline pre-filter:** the existing five-pose Teacher reachability check (`task_reachability`, the same filter the formal scene generation used), at 1 cm steps outward. It gives the kinematic limit r_kin.
  2. **Live bisection** between the last known success and r_kin, using real Teacher episodes in a debug campaign (template `w8d-debug-side-wrist`, cap 4, 8 workers). Each round runs one scene per ray, so 8 scenes per round in parallel.
     - Success means Teacher PASS, i.e. the cup is placed with endpoint PASS.
     - Phase-2 data validity is also recorded, but it is not the boundary criterion.
     - Stop when the bracket is at most 1 cm, or after 3 rounds.
  3. The boundary point B_k is the last success on that ray. Because the boundary can be noisy, the final B_k is repeated once; if the repeat fails, step back 1 cm.
- **Cost:** about 3–4 rounds of 8 Teacher episodes plus one repeat round, about 1.5–2 h of debug campaign time. These are exploration runs, not a formal collection.

## Step 2: uniform sampling inside the boundary

- **Region:** the polygon through B_1..B_8, shrunk inward by 0.01 m, with the place-target exclusion zone and the table/pedestal limits removed.
- **Scene count:** about 103 again: train 83, validation 10, offline_test 10.
- **Sampling:** Poisson-disk sampling with a fixed seed, so points are spread evenly. The minimum spacing is chosen so about 103 points fit, and is never below the formal sampler's 0.004 m. Splits are assigned spatially stratified: validation and offline_test are spread over the whole region, not clustered.
- **Rollout points:** the 4 standard rollout points must fall inside the region and are never training scenes; the spacing rule keeps training scenes at least 0.004 m from them. Each rollout point's distance to its nearest training scene is reported.
- **Gating:** every sampled scene still passes the five-pose reachability filter before it is used.
- **Implementation:** a new pure sampler module (polygon, Poisson-disk, split stratification) with fixture tests, plus a small evidence-side script. Plain decimals in the output, as for the current lists.

## Step 3: what follows (not part of this confirmation)

A new formal scene list means a new qualification and a new formal collection. Per the human's rule (2026-10-19): "如果需要重新采集数据，则先把优化todo里的采集和离线处理的优化做了，再开始采集". So the collection and offline-processing optimisations (to-do items 1–5, 12; antzb queue) land and are gated first. Then: qualification → formal collection → seal → TRAIN-006 (the TRAIN-005 config: dwell compression, speed-ups) → rollout on the 4 standard points.

## Decisions (recommended defaults)

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Centre of the 8 rays | (0.02, −0.29) |
| Q2 | Boundary criterion | Teacher PASS (physical success). Data validity is recorded but does not count. |
| Q3 | Resolution | 1 cm bracket, at most 3 bisection rounds, then one repeat at B_k |
| Q4 | Scene count and splits | about 103; 83 / 10 / 10; spatially stratified |
| Q5 | Inward margin | 0.01 m |
| Q6 | Run the boundary search now, before the optimisations land | Yes. It is exploration (debug campaign), not the formal re-collection. |

## Amendment 1 (2026-10-21, human decision after CP-3761)

The boundary search (EXP-642, EXP-643) found no Teacher failure. Every ray ended at its kinematic limit or at the place-target exclusion, measured in 1 cm steps. Sampling then stopped with `ROLLOUT_POINT_OUTSIDE_REGION`:
- forward_5cm was 9.8 mm from the shrunk edge;
- left_5cm is 0.0603 m from the place target, only 0.3 mm outside the 0.060 m exclusion.

Human decision: "Margin only on reach edges".
- The 0.01 m inward margin applies to edges set by reachability or Teacher success.
- The place-target exclusion is applied exactly, at 0.060 m with no extra margin, as the formal sampler does.
- Rays capped by the exclusion use the exact intersection with the exclusion circle as B_k.
- Every ray is refined offline within its last 1 cm step, at 2 mm steps, with the same five-pose reachability. The refined B_k are then verified live with one Teacher round and one repeat.
- Rollout-point clearance from every scene stays ≥ 0.004 m.
