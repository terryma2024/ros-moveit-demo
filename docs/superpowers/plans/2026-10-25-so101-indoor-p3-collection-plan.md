# SO-101 indoor P3: formal collection with randomised appearance and demonstration diversity — implementation plan

Date: 2026-10-25. The human said "继续P3". These defaults are the recommended ones, recorded under the follow-recommended rule.

Inputs:
- `2026-10-24-so101-indoor-scene-design.md` (P3);
- `2026-10-23-so101-domain-randomization-design-update.md` (R2, R3-a; decisions D1, D2, D3);
- P2 evidence: CP-3787.

## Defaults

| Item | Default |
|---|---|
| Rig | `side-wrist-indoor`. Teacher YOLO `f9cce63b…` (deployed for this rig, CP-3787). |
| Size | **200 committed episodes** in the formal run, plus a qualification run of 40 first. |
| Appearance | 25 % indoor nominal (layout A as is) and 75 % randomised draws over layout A from the `indoor` whitelist: wall, floor and table materials, the indoor lights (intensity 0.7–1.3×, direction), headlight ambient and diffuse, prop visibility, cup colour (excluding colours that blend into the table or walls). Every draw keeps the stripped physics fingerprint equal to nominal (enforced). |
| Held out | Layouts B (lab) and C (home), plus a held-out subset of textures and cup colours, are **never collected**. They are kept for appearance-generalisation evaluation. |
| Teacher source (D2) | Nominal episodes use the camera Teacher (YOLO). Randomised episodes use the **privileged-pose Teacher** (sim-truth cup pose), recorded as `teacher_source: privileged_pose` in the episode identity. |
| Demonstration diversity (R3-a) | On for every episode: `teacher_execution_policy_side_wrist_fast_carry_b_diversity.yaml`. The smoke runs showed no quality loss against carry_b (CP-3784). |
| Scenes | A new Poisson-disk sample in the Teacher success region with a fixed seed. It must be disjoint (≥ 0.004 m) from every existing list and from the held-out lists. The reachability filter is re-run on the **final scene ids** with each scene's diversity values (`refilter_scenes`). |
| Splits | By scene, spatially stratified, plus appearance-asset identity: a texture or cup colour never appears in two splits. |
| Collection | Staged mount mode: phase 1, phase 2, finalize, `--retry-invalid-max-rounds 3`, cap 6, gap 20. Sealed at the end. |

## Tasks

One Sonnet writer at a time. Opus reviews each checkpoint. Fixture tests come first. Every code change gets a full gate, run alone. No source edits while a collection runs.

1. **T1 — per-episode appearance in collection.**
   - The case inputs carry the episode's scene variant, derived deterministically from (campaign seed, scene id) over the `indoor` whitelist, with a flag for the nominal share.
   - The shard realizes the variant MJCF into the task's owned dir and (re)starts the stack with it for that task. Measure the per-task restart cost; batching tasks that share a variant is optional.
   - Record the realized hash and the applied values in `episode.json`, the run identity and the export metadata.
   - The stripped physics fingerprint must equal nominal, otherwise refuse.
2. **T2 — privileged-pose Teacher switch.**
   - The Teacher takes the cup pose from sim truth (`/so101/simulation/evidence` or `scene_state`) instead of the broker `/cup_pose`, behind an explicit `teacher_source` that is frozen with the inputs.
   - It is allowed only on `side-wrist-indoor` randomised episodes.
   - Prove that the camera and privileged pose agree within the existing start-pose tolerance on nominal scenes (a check, not a substitution).
3. **T3 — `refilter_scenes` wired into `act_scene_sample`**, as R3-a to-do 33 requires.
4. **T4 — indoor templates.** Make w8q and w8f templates for `side-wrist-indoor` from the P2-adapted copy, with:
   - the diversity policy;
   - the appearance plan and nominal share;
   - the Teacher-source mapping;
   - the new scene list.

   The existing mount templates stay unchanged.
5. **T5 — qualification run (40 scenes).** Criteria are as for EXP-668: Teacher success, VALID, QC, and the quality gates. Report to the coordinator, who decides on the formal run.
6. **T6 — formal run (200 committed)**, sealed, then merge and export. The training run (TRAIN-009) and its evaluation need separate approval.

## Budget

- Collection is about 141 scenes/h, so 240 scenes plus retries is about 2–3 h of collection.
- Disk: raw bags are about 0.6 GB per episode, so about 150 GB for 240 episodes. Check the evidence partition before T5 and T6, keep at least 50 GiB free, and clean up as needed (logged).
