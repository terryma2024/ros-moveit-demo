# SO-101: migrate every image-baked flow to the mount-tree model — design

Status: decisions confirmed by the human (2026-10-23). Implemented on antzb branch `antzb/mount-migration` (P1, P2, P3 native collection, P5 docs); the P3 broker (M5), M6 and the P4 host cleanup wait for rulings. Gate evidence of each phase is in `progress-item34.md` of the antzb work root.

Human decisions (2026-10-23), all on the recommended option:
- **M1:** mount only.
- **M2:** keep a read-only legacy image-record verifier.
- **M3:** delete most old images. `docker save` three of them: the TRAIN-003..005 source shard and inference images, plus the old mount base `19a57e70`.
- **M4:** retire native collection.
- **M5:** in phase 2, run the broker in mount-base. If its users are no longer used, delete it instead. Phase 3 must check that usage first.
  - **Ruling 2026-10-24 (human):** "Expert Validation 不用了，退役 broker". The broker is retired, together with the Expert Validation production service and its broker-only paths.
- **M6:** in phase 3, make the mounted-source `docker_dev` pattern the standard.
- **M7:** out of scope; note it in the guide only. Human request: "现在 mount tree 的方案已经通了。原始所有将 source build 进 image 的方案都改向这个方案。做一个迁移设计，清理相关历史代码。"

## Why

Mount mode is proven:
- it carried the formal collections EXP-668..671;
- TRAIN-006 used it;
- the parallel rollout ran in mount mode at N=1..6 with all stops proven.

It uses one dependency-only base image (`so101-mount-base`, pinned in `scripts/images/base-image-ids.json`, `check-image --preflight` against the host) plus the host-built install and source trees, mounted read-only from `/data/work/so101-build/mount/<commit12>/` and bound by `BUILD-COMMIT`.

The image-baked path rebuilds 1–20 min of image per commit and keeps a second build and identity chain alive. That chain is the dispatch images, deps records, content identity and the image-mode freeze and readback. It has 44 stale dispatch images on ai-station alone.

## Inventory (read-only map 2026-10-23, HEAD 3732454c6)

| Image or flow | Bakes in | Uses | Mount path today |
|---|---|---|---|
| `campaign-shard` (deps/web/build/final) | web front end, colcon of everything, `/act/source`, `/act/install`, image freeze | collection shards, phase-2 processor, act_rollout shards | **yes**, when the config has `mount_build`. Not the default |
| `campaign-inference` (FROM `parallel-perception`) | source plus pip install, freeze | Teacher (and head) service | **yes**, the same switch |
| `campaign-shard-deps` (FROM `yolo11n-seg-inference`) | apt and pip only | base of campaign-shard | n/a. Its lists already moved to mount-base in antzb `2219211c7` |
| `parallel-perception` | `COPY src/so101_demo_py` into `/opt/venv`, provenance json | perception broker: mujoco parallel batch, teleop expert-validation production service | **no** |
| `yolo11n-seg-inference` | source plus pip install | `perception_launch.py` `docker` runtime (Linux default): text_pick_agent, launch composition | **no** (`docker_dev` bind-mounts source) |
| `yolo11n-seg-train`, `grounding-dino-tiny-train` | source plus pip install | offline training helper scripts | **no** |
| native collection launcher | host install | single-worker collection | Teacher still runs as an **image-mode** container. Native + mount is refused |

**Verification of sealed data never re-runs an image.** `collection_qualification_recompute`, `collection_merge`, `parallel_collection_contracts` and `container_receipts` only compare recorded digests and hashes. So old images are not needed to re-verify sealed roots. The image-mode branch of the **readback verifier** (`_image_problem`, `_report('/act/install')`) is still needed for the about 96 sealed configs without `mount_build`, for example the TRAIN-003..005 source `act-w8f-20261018T235254Z`.

## Decisions (recommended; the human confirms or changes them)

| # | Decision | Recommendation | Alternative |
|---|---|---|---|
| M1 | Campaign roles: shard, processor, Teacher/head service, act_rollout | **Mount only.** `mount_build` becomes required when authoring and starting a new run. The image-mode **production** code goes: the launch branch, the `image_bootstrap` image role, `freeze_image` / `write_build_freeze`, `campaign_shard` `/act/install`, the inference `bootstrap.bash` and the image-mode template authors. | Keep image mode as an off-by-default fallback. That keeps the second chain alive. |
| M2 | Sealed image-mode data | **Keep a read-only legacy verifier.** The image-mode readback checks move into one module, `legacy_image_records`, used only by the verifiers and the recompute. New runs refuse an image-mode config. Tests for these checks stay, as verifier tests. | Delete them and re-seal. Not allowed: sealed roots are never changed. |
| M3 | Old images on the hosts | **Delete the dispatch images**, except the pair behind data that trained a model still in use: `a40fde078e5f…` shard and `3b143177e04a…` inference, the TRAIN-003..005 source. Save those two with `docker save` into `/data/work/so101-build/archived-images/`, with sha256 recorded in the evidence root, then remove them from Docker. Keep the mount base `19a57e70…` as a tar for the same reason; it is the base of the EXP-668..671 sealed runs and the TRAIN-006/007 data.

  **M3 note (2026-10-23, antzb):** the old mount base `sha256:19a57e70…` no longer exists on either host, so it cannot be `docker save`d (only the two training-source images can be archived). Sealed mount runs verify by digest only (`provenance`/`mount_build` records compare the recorded base digest and the tree hashes; no image is run), so nothing is lost. If the old base is ever needed, it can be rebuilt from the pins in git history (`scripts/images/base-image-ids.json`, `docker/mount-base/` at the commits of those runs). `image_content_manifest.py` was removed in P2: the archived tars are checked by plain `sha256sum`. | Keep everything (about 200 GB of images), or delete everything (no re-run is possible). |
| M4 | Native launcher | **Retire native collection.** Parallel staged mount collection is the formal path, and `act_rollout_native` stays as the single-stack rollout reference; it is not a collection. If native collection must stay, its Teacher moves to mount-base. | Port the native Teacher to mount now. |
| M5 | Perception broker (`parallel-perception`) | Phase 2. **Run the broker in mount-base** with the mount tree, replacing `COPY src` with the mounted install. The base must then carry the broker's Python dependencies; check them against `parallel-perception`'s lock first. Its users are the mujoco parallel batch and the teleop expert-validation production service. If either is retired, drop the broker instead: ask the human. | Leave it as is. It is a separate tool chain. |
| M6 | YOLO perception container (`perception_launch` `docker` runtime) | Phase 3. Make the `docker_dev` pattern (bind-mounted source) into the standard, with the mount tree as the source, or move it to mount-base. Remove the baked runtime image. | Keep it. It is outside ACT. |
| M7 | Offline training containers (yolo, grounding-dino) | **Out of scope.** These are developer training tools, not part of the identity chain. Note them in the guide only. | Migrate them too. |

## Phases (after confirmation; one Sonnet writer at a time; Opus review at each checkpoint; fixture tests first; gate green before each push)

1. **P1 — mount mandatory for campaigns (M1, M2).**
   - Code:
     - `config.py` refuses a new config without `mount_build`;
     - `mount_from_config` is the only path;
     - the `launch.py` image branch, the `image_bootstrap` image role, the `provenance.py` image freeze and the `campaign_shard` `/act/install` branch are removed;
     - the legacy readback checks move into `legacy_image_records`, used only by `collection_qualification_recompute` and the merge.
   - Tests: the image-mode production tests are removed or converted to legacy-verifier tests. A fixture proves that a sealed image-mode record still verifies.
   - Templates: the 22 image-mode templates go to `act-templates/archived/`, kept as auditable evidence. The 3 mount templates remain.
   - Evidence: a recompute of one sealed image-mode root and one sealed mount root, before and after the change, gives identical verdicts.
2. **P2 — image build chain removal.** Rebase antzb's `2219211c7`, which removes the campaign-inference, campaign-shard and campaign-shard-deps build chain, onto P1. It also removes `record_deps_installed`, the deps records, `image_content_manifest` (unless M3 uses it for the archived tars), the `BUN_*` / image proxy keys in `scripts/gate/hosts/*.env` that only served image builds, and `build_images.zsh` roles other than mount-base.
3. **P3 — native collection retirement (M4)** and the perception broker (M5), each with its own gate.
4. **P4 — host cleanup (M3).** Save and record the kept images, then delete the dispatch images on both hosts, logged. Scratch images (`so101-webstage-test`, `so101-idtest`, `so101-act-benchmark`, `so101-act-head-search`) need human approval, since they are outside the repo.
5. **P5 — docs.**
   - The architecture guide images row and build sequence; `scripts/images/README.md`; the perception image guide.
   - Old specs and plans get a one-line "superseded by mount mode, 2026-10-23" note, not edits.
   - The optimisation to-do list and the ledger entry.

## Risks

- **A verifier path missed by P1**, for example in the teleop unified admission (`image_source_install`), would refuse the recompute of an old sealed root. Mitigation: the before/after recompute in P1 and an inventory test. Every caller of the image-record shape must be either a legacy verifier or mount-only.
- **The mount base must carry every role's dependencies** (Teacher Ultralytics, broker). The `check-image` must-match list and the per-role import smoke test must cover each role before its image goes.
- **Mount-tree build time** (about 5 min) is now on every commit that runs. It is far below an image rebuild, and it is cached by `<commit12>`.

## Open questions for the human

- **M3:** keep only the two training-source images plus the old mount base as tars, or keep more?
- **M4:** retire native collection?
- **M5:** are the mujoco parallel batch and the teleop expert-validation production service still used?
