# SO-101 ACT: bright indoor nominal scene and appearance library — design

Status: P1 and P2 done (2026-10-25), P3 next (after the coordinator decides on the two INVALID pilot scenes). The human approved the direction ("替换 nominal，先写设计并做效果图原型"), then chose layout A as the nominal and kept B and C as candidates ("用 A（明亮办公室）做为[nominal]，其他环境保留候选（放到repo里），可以进入P1"). P0 and P1 are done; the contact re-activation (item 5 of P1) and every later phase still need the human's confirmation.

## Why

- **R0 (CP-3780) result.** The TRAIN-007A policy breaks under appearance changes: table texture 15/28, blue cup 18/28, green cup 21/28, a 1° side-camera rotation 17/28 and 19/28. It is robust to light intensity, light direction, small camera shifts and fovy.
- **The scene is very dark and unlike a real room.** The current scene (`act/scene_side_wrist.xml`) renders to a mean brightness of about 17/255 on the side camera and about 10/255 on the wrist camera. The background is black, there is no ambient light, there is one key light, and the table is dark brown. Headlight-off is nearly black (the wrist camera drops to 2.9/255), so that R0 bucket is not a meaningful perturbation and is dropped.
- **The human decision:** add an indoor layout (walls, floor, room lighting, background furniture), make it brighter and diverse, and make it the **new nominal**.

## Constraints (unchanged from the randomisation decisions D1 to D3)

1. **Physics unchanged.** Every new element is visual-only: a geom with `contype="0" conaffinity="0"`, static (on the worldbody or on a static body), with no mass and no joint. The robot, table collision geometry, cup and timestep are byte-identical in the compiled physics.
2. **Physics fingerprint v2.** The R0 fingerprint (`act/physics_fingerprint.py`) hashes the compiled `MjModel` physics arrays, so adding geoms changes it. Version 2 drops non-colliding, massless, static visual geoms (and the bodies that only carry them) before hashing. Tests must prove two things: adding the full indoor layout leaves v2 unchanged, and any colliding or massive addition, or any physics change, alters it.
3. **Cameras unchanged.** The `side_camera`, `wrist_camera` and `task_camera` poses, fovy and resolution stay as they are. Nothing new may stand between a camera and the workspace. Walls stand at 1.5 to 2.5 m. Background props stay outside the arm's reach envelope plus a 0.15 m margin and outside the planning scene.
4. **A new rig, not an edited one.** The indoor scene becomes a new rig entry, `side-wrist-indoor` (`rig-v3`). It has the same robot MJCF, URDF, controllers and cameras as `side-wrist` and a new scene file, `act/scene_side_wrist_indoor.xml`. The `side-wrist` rig and its files stay unchanged, because sealed data and the recompute verify against them.
5. **The contact policy receipt.** The approved receipt is keyed on the old scene file hash. The new nominal therefore needs a recorded equivalence: v2 physics fingerprint of old nominal == v2 of new nominal, plus re-activation under the same contact policy. That re-activation is a separate, explicit step in P1, and the human confirms it. The receipt is never bypassed.

## The scene

- **Room:**
  - a floor with a wood, tile or carpet texture;
  - 3 to 4 walls, 2.6 m high, at 1.5 to 2.5 m from the robot base;
  - an optional window panel with a bright emissive or texture "outside";
  - a ceiling plane.
- **Lighting:**
  - a raised global ambient (`<visual><headlight ambient=…>`, since MuJoCo's ambient comes from the headlight);
  - 3 to 5 ceiling lights, directional or spot, with shadows on for the main one;
  - a mild headlight, kept on.
  - **Target:** side and wrist camera mean brightness of about 80 to 130/255 at the nominal settings, with no clipped highlights on the cup. This target is a stand-in until real photos are available.
- **Table:** a light top material (laminate or light wood, plus cloth options). The collision geom is unchanged; only its material and texture change.
- **Background props**, visual-only: cabinets, a shelf, a door, a plant, a poster or whiteboard. They are boxes and cylinders with textures, and meshes only if they are small.
- **Textures:**
  - P0 uses procedurally generated PNGs and MuJoCo built-in textures, so there is no download or licensing question.
  - P1 may add CC0 textures (for example Poly Haven or ambientCG), at 512 to 1024 px, stored under `assets/mujoco/textures/indoor/` with a manifest of sha256, source URL and licence.

## The appearance library (for randomisation, R2)

Each episode draws from the library:
- wall colour or texture;
- floor;
- light configuration: count, colour temperature, intensity 0.7 to 1.3×, direction;
- prop layout: positions within the allowed zone, and which props are present;
- table material;
- cup colour, from a set that excludes colours that blend into the table or walls.

### Asset pools (antzb goal 13, CP-3788)

- **Procedural textures.** `act/indoor_assets.py` generates 8 families (wood, parquet, tile, fabric, plaster, laminate, concrete, wallpaper) x 104 = 832 textures from parameters and a seed (OKLab/OKLCH colour, numpy `Generator`). `proc-manifest.json` (committed, 500 KB) lists parameters, seed, PNG sha256 and decoded-pixel sha256 per texture. No PNG is in git: `scripts/assets/gen_indoor_textures.py --procedural --out DIR` and the mount-tree build hook materialise them (about 184 MB per install tree) and fail with `INDOOR_TEXTURE_NOT_REPRODUCED` on any pixel difference.
- **CC0 pack.** 180 Poly Haven colour maps (wall 55, floor 60, table 65), 1K resized to 512 px, kept **outside git** as a separate pack (71 MB PNG; the 1K JPG originals are kept beside it). `cc0-manifest.json` (committed) is its identity (source URL, asset id, CC0, download date, sha256 before and after resize, `pack_sha256`); `CC0-LICENSES.md` is the human-readable list. The build copies it from `INDOOR_CC0_PACK` when set. `scripts/assets/fetch_cc0_textures.py` reproduces the selection.
- **Cup colour.** Continuous HSV in 36 hue bands of 10 degrees. A draw is accepted only if its OKLab distance to the drawn wall, floor and table colours (texture mean x tint) and to the red landing ring exceeds `MIN_DELTA_E` (wall 0.12, floor 0.08, table 0.15, ring 0.15); up to 64 attempts, else the draw is rejected.
- **Splits by identity.** Seeded (`MASTER_SEED` 20261025), 70/15/15 by texture group (family, or CC0 surface) so that every family is in every split; hue bands 26/5/5. The three pools are disjoint (`check_split_disjoint`). Layouts B and C and the val/test assets are never collected for train.

Draws come from the R0 scene-variant module (`act/scene_variant.py`), extended with an `indoor` whitelist. Every draw records its realized hash and stays within the v2 physics-fingerprint invariance. The split is assigned by asset identity (no texture shared between train and test).

## Teacher perception (decision D2)

- The `task_camera` YOLO sees a new scene. It must be checked on the new nominal: detection rate and localisation error against simulation truth.
- If it passes, nominal episodes may keep the camera Teacher.
- Randomised-appearance episodes use the privileged-pose Teacher (`teacher_source: privileged_pose`).
- YOLO is fine-tuned on renders of the appearance library, with labels from simulation truth.

## Phases

| Phase | Content | Exit evidence |
|---|---|---|
| **P0 (now)** | Prototype only, outside the repo source: 3 indoor layouts (A bright office, B lab with shelves, C warm home with a window) built as scene files in an evidence root. Render side, wrist and task cameras at 3 poses (reset, pre-grasp over the cup, place). Report mean brightness, a nominal-vs-indoor comparison, and whether the v1 fingerprint changes (it will, which is expected) and what v2 must exclude. | Images for human review |
| P1 (done) | Rig `side-wrist-indoor`, scene and texture assets, physics fingerprint v2 with tests, the receipt equivalence and re-activation (human confirm), and the scene-variant `indoor` whitelist | Gate green, fingerprint tests, renders from the real stack |
| P2 | YOLO check on the indoor nominal plus a fine-tune if needed; a 20-episode pilot collection (Teacher success, data chain) | Pilot report |
| P3 | Collection of 200 to 300 episodes with randomised appearance (privileged Teacher) | Sealed, QC, ledger |
| P4 | TRAIN-009 (TRAIN-007A config plus the image augmentation decision) | Training evidence |
| P5 | Evaluation: indoor held-out and R0-style buckets (2 trials per scene, paired comparison against TRAIN-007A) | Report |

## Open questions for the human

- Photos of the real work cell (camera views, background, light) would let the nominal layout and brightness be matched to the real robot instead of being invented.
- After P0, which layout or layouts become the nominal? The others are then randomisation members.

## P1 status (2026-10-24)

Done and gated (code commit `9e5e90e20`, gate `9e5e90e20c1b` green, 15532 demo tests). Evidence root `/data/work/so101-evidence/indoor-scene/p1-20261024/` (`manifest.md`).

- **Assets.** Layout A is the nominal scene `act/scene_side_wrist_indoor.xml`. B (lab) and C (home) are candidates in `act/indoor/` (`scene_side_wrist_indoor_lab.xml`, `scene_side_wrist_indoor_home.xml`); no rig loads them. Each scene is a standalone file (the three layouts share no include, because they differ in most elements). The 16 procedural textures are in `assets/mujoco/textures/indoor/` with `manifest.json` (sha256, size, seed, command), made by `scripts/assets/gen_indoor_textures.py`. `setup.py` installs every file under `assets/`, so the new directories need no install rule.
- **Rig.** `side-wrist-indoor` (`config/act/rig-v3.yaml`) has the robot MJCF, URDF, plugins, controllers, cameras and state of `side-wrist` and only a new scene. The `side-wrist` and `head-wrist` files and their profile identity digests are unchanged (checked against the base commit); the indoor files are foreign to both digests. The camera-only lookups (`rig_from_observation`, `rig_from_frame_keys`, the training config) still resolve to `side-wrist`, because the observation is identical. `rig-v3.yaml` is a permanent entry of the versioned-name allowlist, like `rig-v1.yaml` and `rig-v2.yaml`. The contact collector has no scene or model pin for the indoor rig, so contact calibration is refused for it until the re-activation is confirmed.
- **Fingerprint.** `act/physics_fingerprint.py` keeps v1 unchanged and adds the stripped fingerprint (`stripped_physics_fingerprint*`, record `fingerprint_version: 2`; the versioned-name guard forbids `v2` in identifiers). It removes geoms with `contype == 0` and `conaffinity == 0`, the bodies and meshes that only they carry, and the asset-path counts (`npaths`, `mesh_pathadr`, `hfield_pathadr`), and refuses a strip that changes any body mass or inertia. Tests: nominal side-wrist, A, B and C are equal under v2 and differ under v1; a colliding box, a friction edit, a mass edit, a collision-geom size edit, a timestep edit and a joint damping edit each change v2; the mass guard fires on a stripped geom that carries mass.
- **Variant whitelist.** `act/scene_variant.py` accepts `"base": "indoor"` with wall, floor and table texture and tint, per-light diffuse, dir and active, headlight, prop visibility and cup colour. Physics and camera fields stay refused. `scene_variant_run` enforces the v2 equality with the nominal for every realized indoor variant; its record says `fingerprint_version: 2`.
- **Receipt equivalence (evidence only).** The v2 fingerprint of the old nominal equals that of the new nominal, B and C, and the 462 compiled physics arrays are identical (`equivalence-record.json`). No receipt was created or modified and no activation ran. **Human step owed:** confirm the contact re-activation for the indoor scene.
- **Real stack.** The `side-wrist-indoor` stack came up headless from the mount tree. Frame means from the camera topics: side 112.17, wrist 75.74, task 118.16, equal to the offline render (112.17, 75.68, 118.16). The textures, shadow and room lights render in the camera plugin.

## P2 status (2026-10-24)

The contact activation for `side-wrist-indoor` is derived and approved (CP-3783). The YOLO check on the indoor nominal is below the stop criterion: 28 of 32 positions detected (87.5 %, old nominal 32 of 32), median xy error 0.49 mm in both scenes. The four misses are a second cup instance on the red landing ring plus the cup's cast shadow. The pilot collection has not run. Open decision: switch the shadow of `ind_main` off in the nominal scene (a new scene hash and a new derived activation) or fine-tune YOLO on indoor renders.

### P2 result (2026-10-25, CP-3787)

The Teacher's YOLO is fine-tuned on indoor renders and deployed for `side-wrist-indoor` only (`act/teacher_model.py`; the other rigs keep the old weights). 32-position check: 32 of 32 detected, median xy error 0.50 mm (stack samples of the four standard points 4 of 4). Pilot on 24 new scenes (two staged runs of 16 and 8): Teacher PASS 24 of 24, data VALID with QC PASS 22 of 24; the two INVALID are recording losses (topic loss, source gap), not Teacher failures. No scene file changed.
