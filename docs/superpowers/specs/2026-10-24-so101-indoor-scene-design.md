# SO-101 ACT: bright indoor nominal scene and appearance library — design

Status: draft (2026-10-24). The human approved this direction: "替换 nominal，先写设计并做效果图原型". Only P0 (prototype renders) is authorised. Every later phase needs its own confirmation.

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
| P1 | Rig `side-wrist-indoor`, scene and texture assets, physics fingerprint v2 with tests, the receipt equivalence and re-activation (human confirm), and the scene-variant `indoor` whitelist | Gate green, fingerprint tests, renders from the real stack |
| P2 | YOLO check on the indoor nominal plus a fine-tune if needed; a 20-episode pilot collection (Teacher success, data chain) | Pilot report |
| P3 | Collection of 200 to 300 episodes with randomised appearance (privileged Teacher) | Sealed, QC, ledger |
| P4 | TRAIN-009 (TRAIN-007A config plus the image augmentation decision) | Training evidence |
| P5 | Evaluation: indoor held-out and R0-style buckets (2 trials per scene, paired comparison against TRAIN-007A) | Report |

## Open questions for the human

- Photos of the real work cell (camera views, background, light) would let the nominal layout and brightness be matched to the real robot instead of being invented.
- After P0, which layout or layouts become the nominal? The others are then randomisation members.
