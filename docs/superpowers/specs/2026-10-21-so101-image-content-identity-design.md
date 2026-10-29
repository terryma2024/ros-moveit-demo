# SO-101 ACT: build images on each host and prove they are equivalent — design and plan

> Superseded by mount mode, 2026-10-23: campaigns run from `so101-mount-base` with host-built mounted trees, so the per-commit image build, the deps records and the image content manifest were removed (migration P2). Kept as history.

Status: CONFIRMED by the human on 2026-10-21 ("可以，按推荐执行。 Q4 pyc不生成").
- Q1–Q3 and Q5 are as recommended.
- **Q4 is changed: no `.pyc` is generated.** The builds use `PIP_NO_COMPILE=1`, setuptools `--no-compile` and no `compileall`. A test asserts that the manifest holds no `*.pyc` under `/act` or `/act/venv`, and none in site-packages added by our builds.

Option 2 was chosen on 2026-10-21 ("可以，按方案2写设计文档").

**Amendment 1 (2026-10-21, human: "可以，按这个做").** The shard-deps base no longer reproduces the exact apt versions of the current shard image. Those old ROS builds are no longer on the mirrors, which keep only the newest build, and inside `docker build` `packages.ros.org` reached only about 32 KB/s from antzb.
- **Sources.** The shard-deps build switches its apt sources to `mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu` (same keyring) and `mirrors.tuna.tsinghua.edu.cn/ubuntu`, and pip stays on the tuna PyPI mirror. It installs the mirror's current versions.
- **Lock file.** The installed apt (`dpkg-query -W`) and pip (`pip freeze --all` with hashes) sets are exported into a tracked lock file under `scripts/images/`, as a record and for later comparison.
- **One build, pinned by ID.** The base is built once on ai-station, pinned by ID in `prepare-image-build.py`, and transferred once (zstd) to antzb. A shard-deps built on antzb is used only to validate the build flow.
- **Requalification.** The ROS packages in the shard image move from the June builds to the mirror's current builds. Adopting the new images therefore needs a gate and a qualification, after the current formal collection.

## Why

- **The link is slow.** ai-station and antzb are on different networks, and tailscale reaches about 2.8 MB/s between them, so transferring a full image pair (about 31 GB) takes hours.
- **Two-host collection compares image IDs today.** It needs the same images on both hosts because the controlled identity compares the docker image ID. Two independent builds never share an image ID.
- **The goal:** build on each host, and admit a multi-host collection only when the two images are proven to have the same content.

## What exists today (survey 2026-10-21)

**Identity.** The controlled identity key `image_source_install` is `{inference, shard}`. Each entry is `{digest, package_source_sha256, install_sha256}`, validated in `runtime/inference/config.py:66-71` and built in `so101_teleop/unified/admission.py:244-245`.
- `digest` is the local docker image ID (`docker image inspect .Id`). The campaign never uses a RepoDigest.
- `package_source_sha256` and `install_sha256` are already content hashes. `runtime/container_campaign/provenance.py` (`_tree`, `write_build_freeze`, `main`) computes them over `/act/source` and `/act/install`. It hashes regular files (sha256, size, mode) and relative symlinks, and ignores mtimes. The values are frozen at build time in `/act/provenance.json` and read back inside every started container.

**Checks that compare the image ID**, each of them a refusal:
- `shard_owner.py:70`, `processor_owner.py:75`: the config ID against the launch record;
- `registry.py:177`: the owner against the registered launch;
- `shard_owner.py:166-171`, `processor_owner.py:135-137`, `service_owner.py:206-222`: the inspect ID after start against the config;
- `act/collection_qualification_recompute.py:165-173, 247-249, 300-340`: the offline re-check of qualification.

**Not covered by any content hash:** everything outside `/act`. That is `/opt/ros`, the venv site-packages, system libraries, apt packages, the glvnd EGL file, `/act/venv`, `/act/provenance.json`, `/act/image-role` and `bootstrap.bash`. `act-image-dependencies.json` (pip and apt version lists) is inside `install_sha256`, so a version difference already shows up there, but not a byte difference.

**Sources of build nondeterminism:**
- The **shard** Dockerfile is the main one:
  - unpinned `apt-get update && apt-get install` (lines 46-55);
  - pip from a mirror with top-level pins only, with no hashes and no transitive pins (lines 56-60);
  - `--network default`.
- The **inference** build is offline (`--network none`, `pip install --no-deps` of the snapshot).
- **Others:**
  - compiled C++ output (colcon; RelWithDebInfo; 4 parallel workers);
  - `.pyc` files written by pip and setuptools at install time;
  - file mtimes.
- **Base images** are pinned by ID in `scripts/images/prepare-image-build.py:50-55`.

## Design

### 1. Image content manifest: a full root filesystem, computed outside the container

A new tool, `scripts/images/image_content_manifest.py`, with tests:
- **Input.** The image is read from `docker save <image-id>` (a tar stream), never from inside a running container, so the result does not depend on code in the image.
- **Merge.** The layers are merged in order, following the OCI rules: whiteouts (`.wh.<name>`), opaque directories (`.wh..wh..opq`) and hard links.
- **One entry per path** of the final root filesystem:
  - type (file, dir, symlink, hardlink target, device or fifo);
  - mode and uid/gid;
  - for a regular file, its size and sha256;
  - for a symlink, its target.
  - Mtimes, atimes and ctimes are not recorded.
- **Image config fields** that change behaviour: `Entrypoint`, `Cmd`, `Env`, `WorkingDir`, `User`, `ExposedPorts`, `Volumes`, `Labels` and `Shell`.
- **Output.**
  - `image-content-manifest.json`: canonical JSON, sorted, with plain strings.
  - `content_sha256`: the sha256 of the canonical manifest bytes.
  - An `excluded` section listing every path dropped by an exclusion rule, with its rule and its own hash, so an exclusion stays visible.
- **Exclusion list** (`scripts/images/image-content-exclusions.txt`, tracked and tested). Each entry is a glob, a reason and the date added. The initial entries, each kept only if the first determinism test (below) shows it varies:
  - `/var/log/**` (apt and dpkg logs);
  - `/var/cache/**`, `/var/lib/apt/lists/**` (the apt index; the installed set is still checked through `/var/lib/dpkg/status` and the files themselves);
  - `/tmp/**`;
  - `/root/.cache/**`.

  Anything not excluded must match. An exclusion cannot cover `/act/**`, `/opt/ros/**`, `/usr/lib/**`, `/usr/bin/**` or `/act/venv/**`, and a test enforces this.
- **Diff mode.** `image_content_manifest.py diff A.json B.json` lists every differing path with both sides, grouped by top directory and by dpkg or pip package where a path can be attributed (from `/var/lib/dpkg/info/*.list` and pip `RECORD` files).

### 2. Identity: content in the logic class, image ID in the environment class

This follows the confirmed logic/runtime design (2026-10-19) and the multi-host design (Q3, where `gpu_uuid` moved to the environment class).
- **Logic class.** `image_source_install.<role>` becomes `{content_sha256, package_source_sha256, install_sha256}`.
- **Environment class.** The image ID moves to a per-host record, `host/image-registration.json`: host, image ID, `content_sha256`, the manifest path and sha256, and the build directory.
- **Refusal checks that keep using the image ID,** now against the host's registration instead of the controlled identity:
  - `shard_owner.py:70` and `processor_owner.py:75`: config against launch;
  - `registry.py:177`;
  - the post-start inspect checks.

  They prove "this container runs the image this host registered". The registration proves that image has the identity's `content_sha256`, so the chain is unbroken.
- **The registration is written by a registration step** that computes the manifest from `docker save` on that host. It refuses if `content_sha256` differs from the identity. Admission requires a registration for the image ID in the config. Qualification recompute and the sealed records check `content_sha256` and the two in-image hashes, and record the image ID as environment.
- **Readability of old records:** a v1 identity (with `digest`) stays readable and is checked as today, and the identity-version rule from item 1 applies. `act_merge_collections` compares `content_sha256`, never the image ID.

### 3. Make the two builds produce the same content

1. **Shard dependency base.** Move the networked shard steps (apt lines 46-55, pip lines 56-60) into a new base image, `so101-campaign-shard-deps`.
   - It is built once (on ai-station), pinned by ID in `prepare-image-build.py` like the other two bases, and transferred once per change. It changes rarely: only when the apt or pip set changes.
   - In that build, pin apt by exact `pkg=version` from the env-align manifest (`scripts/env`), and pin pip with a fully resolved lock file plus `--require-hashes`.
   - The shard build then runs `--network none`, like inference.
2. **Python bytecode (Q4 as decided).** No `.pyc` is generated at build time:
   - `PIP_NO_COMPILE=1` for every pip install;
   - setuptools / colcon Python installs use `--no-compile`;
   - no `compileall`.

   `PYTHONDONTWRITEBYTECODE=1` already stops runtime writes. The images' file systems are read-only at run time anyway.
3. **Compiled C++.**
   - Add `-ffile-prefix-map=/act/=/act/` and `-fdebug-prefix-map`; the build paths are the same in both builds already.
   - Do not use ccache in image builds.
   - Keep the parallel-worker count from changing output; the determinism test checks it.
   - Fix any use of `__DATE__` or `__TIME__` found by the diff.
4. **Snapshot copy.** File mtimes are not part of the manifest, so `shutil.copy2` can stay.

### 4. Acceptance tests, in this order

1. **Same host, two builds.** Build the shard and inference images twice on ai-station, from clean build directories, at the same commit. The two `content_sha256` must be equal. If they differ, use the diff to fix the build. The exclusion list may grow only with a justified, tested entry, and never inside the protected trees.
2. **Two hosts.** Build on ai-station and on antzb at the same commit, from the same three pinned bases (the shard-deps base transferred once). The `content_sha256` must be equal, with a diff report.
3. **Campaign path.** On each host, a debug campaign of 8 scenes runs with its own image ID and the shared `content_sha256` (the registration step, admission and the provenance checks). The two sealed indexes then merge with `act_merge_collections`.

### 5. Until this lands

Formal two-host collection uses the build-once path: a localhost registry on ai-station, reached from antzb through an ssh tunnel, pushes only the missing layers. The image ID is identical, and the identity stays as today.

## Implementation plan

Sonnet writers, Opus review, fixture-only tests first, the repo gate, one writer per area.

1. `image_content_manifest.py` and the exclusion list, with tests on synthetic layer tars covering whiteouts, opaque dirs, hard links, symlinks, the exclusion rules, the protected-tree guard, canonical bytes and diff attribution.
2. The shard-deps base:
   - a Dockerfile split, apt pinned from the env manifest and pip with a hash lock;
   - `prepare-image-build.py` pins the new base;
   - the shard build runs with `--network none`;
   - `SOURCE_DATE_EPOCH` and the compiler flags.
3. Acceptance test 1 on ai-station, with fixes until the two builds are equal.
4. The identity change: the registration step, the logic/environment split of `image_source_install`, the refusal checks rewired to the registration, the qualification recompute and the v1 readability. Each refusal gets a test. This depends on item 1's identity v2, which is coming from antzb.
5. Transfer the shard-deps base to antzb once, then acceptance test 2.
6. Acceptance test 3, together with the two-host dry run of the multi-host design (8 + 8 debug scenes, merge, export).

## Decisions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Where to pin the networked shard steps | A separate shard-deps base image, built once and pinned by ID, rather than pinning apt and pip inside the shard build. Then the per-commit build is offline on both hosts. |
| Q2 | Exclusion list | Start with the 5 globs above, keep only those the first determinism test proves variable, and never exclude inside `/act`, `/opt/ros`, `/usr/lib`, `/usr/bin` or `/act/venv`. |
| Q3 | Image ID in identity | It moves to the environment class (per-host registration). `content_sha256` and the two in-image hashes are the logic identity. |
| Q4 | `.pyc` handling | **Decided: no `.pyc` is generated** (the human changed the recommendation). The draft had recommended `SOURCE_DATE_EPOCH` with checked-hash `.pyc`. |
| Q5 | Order with other work | After antzb's item 1 (identity v2) is merged. Formal two-host collection before then uses the registry path (§5). |
