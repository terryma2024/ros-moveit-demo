# Images and mount trees

Every ACT campaign role (the Teacher service, collection shards, phase-2 processors, `act_rollout` shards) runs in one image,
`so101-mount-base`. The image holds the dependencies only (apt packages, the Python lock, ROS Jazzy). The project code is built
on the host and bind-mounted read-only, so a new commit needs a tree build of about 5 minutes and no image build.
Design: `docs/superpowers/specs/2026-10-21-so101-mount-build-images-design.md`; the migration that removed the image-baked
campaign images: `docs/superpowers/specs/2026-10-23-so101-mount-tree-migration-design.md`.

| File | What it does |
| --- | --- |
| `build_images.zsh [--host H] [--no-cache]` | Builds `so101-mount-base` (the only role) from `docker/mount-base/` through `prepare-image-build.py`. Host values (evidence root, `BUILD_PROXY`) come from `scripts/gate/hosts/<host>.env`. |
| `prepare-image-build.py` | Prepares the build context and the pinned inputs of the role, and records the build under `<evidence root>/image-build-<stamp>`. |
| `base-image-ids.json` | The pinned base image id of `so101-mount-base`. |
| `build_mount_tree.zsh --commit HEX [--host H \| --build-root DIR]` | From a clean worktree at HEX, builds `<build root>/mount/<commit12>/{install,source}`, writes `BUILD-COMMIT` last, then makes both trees read-only. |
| `start_mounted.zsh` | Starts one headless stack in the base image with the two trees mounted read-only; the entry script refuses a tree whose `BUILD-COMMIT` is not the given commit. |

`docker/mount-base/apt-packages.txt` was first taken from the installed set of the shard-deps image (`shard-deps-apt-installed.tsv`,
453 names). That image, the tsv and `image_content_manifest.py` are gone; the list now stands on its own and `apt-pins.txt` holds the versions.

## Workflow for a run

1. The gate is green at commit C (`scripts/gate/run_host_gate.zsh`).
2. `build_mount_tree.zsh --commit C --host H` (the submodule `third_party/mujoco_ros2_control` must be initialised).
3. `python3 scripts/env/image_env.py capture-image --image <base image id> --output M.json` records what the base contains once per base;
   `python3 scripts/env/image_env.py check-image --manifest M.json --tree <install tree> --preflight <file>` compares the host with it and
   writes the record a campaign start requires (`mount-preflight-<commit12>.json` in the evidence root); exit 0 means no must-match difference.
4. The campaign config names `mount_build` (`{commit, root}`); `mount_from_config` is the only launch path. A config without it is refused
   (`MOUNT_BUILD_REQUIRED`).

The base is rebuilt only when the host pins move (`check-image --preflight` reports the difference as a must-match failure).

## Sealed image-mode records

About 96 sealed campaign configs predate the mount trees and name self-contained images. They are read, never launched:
`so101_demo.act.legacy_image_records` compares the recorded digests, the recorded readback and the identity, and
`scripts/migration/recompute_before_after.py` checks that a recompute of a sealed root gives the same verdict before and after the
migration. No image is needed to re-verify a sealed root.

## Other images

`so101-parallel-perception` was the perception broker image. The broker, `docker/parallel-perception`, `scripts/parallel-perception-container.sh`, the mujoco parallel batch that served it and the Expert Validation production service were retired on 2026-10-24 (migration M5, commit P3b); the image was deleted from antzb on 2026-10-24 (P4). The macOS two-worker service campaign is kept; it runs its MPS broker in-process and uses no image. One explicit gate still names the image as its default (`benchmark_test/test_act_scene_perception_gate.py`, overridable with `SO101_ACT_SCENE_GATE_IMAGE`; it skips when the image is absent). The offline training images (`yolo11n-seg-*`, `grounding-dino-tiny-train`) are separate tool chains; they are not built here.

The YOLO perception container (`perception_launch` `docker` runtime) holds dependencies only. Its Python source is the `so101_demo` package of the running build, bind-mounted read-only (migration M6; `docker_dev` is retired, `docker` is the same pattern). The image is rebuilt with `scripts/yolo-seg-inference-container.sh build`; it contains no `so101_demo` package.
