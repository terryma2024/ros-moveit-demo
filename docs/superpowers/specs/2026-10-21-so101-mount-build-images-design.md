# SO-101 ACT: dependency-only images with the build mounted — design and prototype result

Status: CONFIRMED-by-coordinator (review of 4f3300f8d). The principle comes from the human's instruction of 2026-10-21; the four decisions
below were taken by the coordinator, following the recommendations. Nothing here is on the main branch, and no collection code
(provenance, launch, config) is changed until step 7 of section h has been reviewed.
Requested by the human on 2026-10-21. Prototype and measurements: antzb, `progress-mount-images.md` in the run directory.

## Why

The shard image takes about 20 minutes to build (1103 s on antzb, almost all of it colcon compiling C++), and every commit needs a new
one. The gate already builds the same install tree on the host, with ccache. The idea: the image holds only the dependencies, and the
container gets the host-built `install` tree and a source snapshot as read-only bind mounts.

The image is then built once per dependency change. A commit costs a host build the gate has already done.

## What the prototype showed (antzb, 2026-10-21)

Base image: the shard-deps image built for item 23 (`sha256:c2fa39d79363…`), which has no `/act/install` and no `/act/source`.
Mounted tree: `/data/work/so101-build/gates/94ceb9258a49.inv/install`, built by the gate, read-only. Container flags unchanged
(`--read-only --cap-drop ALL --network none`, no-new-privileges, one GPU).

| Check | Result |
| --- | --- |
| Headless execution stack from `so101_mujoco_act_execution_stack.launch.py` | Starts; arm, neck, gripper and joint-state controllers activate; `mujoco_ros2_control_node` runs |
| `task_reachability --ik-backend native`, point p1 | `REACHABLE`, 7 of 7 segments accepted; targets and verdicts equal to the run from the built shard image |
| Mounted at the build path, and mounted at `/act/install` | Both start and answer the same, because the setup scripts honour `COLCON_CURRENT_PREFIX` |
| GPU rendering | EGL uses the NVIDIA device once the glvnd vendor file is present (see F3) |

It did not work out of the box. Each failure below has a cause and a fix that the design has to carry.

- **F1, a stale `so101_demo` shadows the mounted one.** The base's `act-runtime.pth` runs `sys.path[:0] = [...]` with `/opt/venv` in it,
  and `/opt/venv` holds an old copy of `so101_demo`. A `.pth` prepends after `PYTHONPATH` is read, so `PYTHONPATH` from `setup.bash`
  loses. Launch failed with `No module named 'so101_demo.runtime.launch_composition'`. Fix: the base must not carry project code, and
  the `.pth` must name the mount point (`/act/install/...`) rather than a path that does not exist.
- **F2, 88 installed scripts start with `#!/usr/bin/python3`.** The gate runs colcon with the system interpreter, so the console scripts
  use system Python, which has none of the venv packages. `scene_setup` died on import. Fix: build the mounted tree with the
  interpreter that the container has at the same path (section c), or export the venv `site-packages` on `PYTHONPATH` for system Python.
  The prototype did the second.
- **F3, the base has no NVIDIA glvnd vendor file.** The shard Dockerfile adds `10_nvidia.json`; the deps image does not. Without it
  EGL falls to Mesa llvmpipe (camera frames 195 ms, `CAMERA_RENDER_SLOW` on every frame). With the file bind-mounted there was one such
  warning. The file belongs in the base image.
- **F4, the base has no `/act/bootstrap.bash`.** The mounted run needs its own entry script. It sources `/opt/ros/jazzy/setup.bash`,
  then `<mount>/setup.bash` with `COLCON_CURRENT_PREFIX` set.
- **F5, versions differ between host and base, and it still ran.** Of 1062 packages in the deps image, 851 have the same version as the
  antzb host, 208 differ (121 of them `ros-jazzy-*`, for example `ros-jazzy-action-msgs` 2.0.4 build 20260911 on the host, 20260612 in
  the image), and 3 exist only in the image. The stack worked with this drift. That is luck, not a guarantee, so section b defines
  what must match.
- **F6, the gate tree contains `.pyc` files and build paths.** `__pycache__` directories exist under `install`, and two generated
  `rosidl_generator_c` libraries embed the build path as a string. A content hash of that tree is only stable if the pyc files are
  excluded or never written, and if the build path is the same on every host. Two image builds of one commit also differed in 37 generated files (rosidl `*_description.c`, `*_type_support.c`, `Cargo.toml`, and the type hashes in them) because rosidl orders referenced types from Python sets; the host build needs `PYTHONHASHSEED=0` too.

## Design

### a. Base image

Content: Ubuntu 24.04, ROS Jazzy and the apt packages the stack needs, the pip set in the venv, the NVIDIA glvnd vendor file, the
entry script, and the `.pth`. No `so101_*` code, no `/act/install`, no `/act/source`.

It is the item-23 shard-deps image plus the inference dependencies it already inherits, with two changes: the vendor file and the entry
script move in, and the stale `/opt/venv/.../so101_demo` goes out (the inference base is rebuilt without it; a `rm` layer is not acceptable, because the data stays in the lower layer and the manifest gets harder to read). It is built once, with the Tsinghua apt and PyPI mirrors and the hashed lock (item 23), pinned by image ID in
`scripts/images/base-image-ids.json`, and recorded in `shard-deps-apt-installed.tsv` and `shard-deps-pip-installed.txt`. Build time on
antzb with the mirrors: 97 s.

The inference image has the same shape and gets the same treatment.

**Rule:** the base images contain no `so101_*` code. A test over the Dockerfile and a check over the image manifest (no path or
distribution named `so101_*` under `/act`, `/opt/venv` or any `site-packages`, except the mounted tree) enforce it.

### b. Proving the environment matches

Mounted artifacts run against the container's libraries, so the container must agree with the host that built them. The base image's
manifest is the reference, and both hosts are aligned to it with the tool that aligned antzb to ai-station (`so101_env.py apply`, with
the same hold mechanism). Extend `scripts/env/so101_env.py`:

- `capture --image IMAGE_ID` runs `docker run --rm --network none --read-only --entrypoint …` and reads `dpkg-query -W`, `pip freeze
  --all` for `/act/venv`, `/etc/os-release` and the python minor version out of the image, and produces the same manifest schema.
- `apply --manifest IMAGE.json` brings a host to that manifest, and `check --manifest IMAGE.json` compares.

The must-match set is everything the host and the image share, plus what the mounted tree needs:

1. every apt package installed in **both** the host and the image: the versions are equal (this is what `apply` achieves);
2. for packages only the image has, the dependency closure decides: the `ros-jazzy-*` packages in the closure of the mounted packages
   (`package.xml` `depend`, `exec_depend`, `build_depend`, resolved as `repo_dependency_keys` does) and the apt package that owns each
   `DT_NEEDED` library of every ELF file in the mounted tree (found by running `ldd` over the tree inside the image and mapping files
   to packages). A package in this set that the host lacks is a refusal, because the host build could not have linked against it;
3. `python3` minor version, Ubuntu codename, and the venv pip set (name and version).

Any mismatch is a refusal (exit 1) with the diff table. Packages only the host has are reported, not refused. The check runs on the
host before the container starts and its result is stored next to the run evidence. Step 6 of the plan builds against a deliberately
skewed host and shows that the check refuses it.

### c. Host build, and where absolute paths come from

Use the gate's build tree when the gate has built the commit, or a dedicated root for builds that are not gated. Both hosts have
`W=/data/work`, `BUILD_ROOT=/data/work/so101-build` and `TEST_VENV=/data/work/venvs/so101-act-test`, so one path works on both
hosts: `/data/work/so101-build/mount/<commit12>/install`. The container mounts it **at the same path**. Same-path mounting is the
rule, even though the prototype also ran from `/act/install`, because it keeps every embedded path true and keeps the content hash the
same on both hosts.

Sources of absolute paths in an install tree, checked in the prototype tree:

| Source | Count in prototype | Effect if the mount point differs | Handling |
| --- | --- | --- | --- |
| `setup.*`, `local_setup.*`, `package.*` fallback prefix | 44 text files in all | none while `COLCON_CURRENT_PREFIX` is set | entry script sets it |
| `share/ament_index/resource_index/parent_prefix_path/*` | 9 | wrong parent prefix for tools that read it | same-path mount |
| script shebangs `#!/usr/bin/python3` | 88 | system Python lacks the venv packages (F2) | see below |
| `RUNPATH` with the install `lib` directory | 1 library | none (`LD_LIBRARY_PATH` from the setup scripts finds it) | same-path mount |
| strings in `librosidl_generator_c` objects | 2 libraries | hash differs between paths | same-path mount, plus `-ffile-prefix-map` |
| `__pycache__/*.pyc` | many | hash differs by mtime | build with `PYTHONDONTWRITEBYTECODE=1` and `--no-compile`; hash check rejects any `.pyc` |
| CMake package configs | none absolute | none | none |

Shebangs: run the mounted build with an interpreter at a path that exists in both worlds. The base creates its venv at
`/data/work/venvs/so101-act-test` (the host's `TEST_VENV` path); colcon runs from it on the host; the shebangs then name that path and
resolve in the container. This needs the host venv and the image venv to hold the same packages, which section b already checks. If that
turns out too strict, the fallback is the prototype's `PYTHONPATH` entry.

Source snapshot: `git archive` of the commit into `/data/work/so101-build/mount/<commit12>/source`, mounted read-only at the same
path. It carries `.image-git.json` as now.

### d. Identity and provenance

Today `provenance.py` freezes the hashes of `/act/source` and `/act/install` into the image at build time and reads them back at
container start. With mounts, there is nothing to freeze in the image.

- **Host side:** compute `install_sha256` and `package_source_sha256` over the mounted trees with the same tree rule as the content
  manifest (path, type, mode, size, sha256; `__pycache__` and `.pyc` rejected, not skipped; uid and gid normalised). These two values
  stay in the logic class of the identity, as in the content-identity design.
- **Container side:** at start, recompute both hashes over the mount points inside the container and compare with the values from the
  launch record. A difference is a refusal (`IMAGE_PROVENANCE_INVALID` family). The mounts are read-only, so the tree cannot change
  after the check, and the check runs again where the readback runs today.
- **Image ID:** identifies the base only. It stays in the environment class; the base is the same file set on both hosts when the
  base image is transferred once (g).

This changes `provenance.py`, `image_bootstrap`, the launch record and the config validation (`runtime/inference/config.py:66-71`). None
of that is touched until the coordinator approves; it is logic and needs the approval gate.

### e. Security

Unchanged: `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--network none`, `--ipc private`, a non-root user.
New: the mounts are `readonly`, and the host paths are the commit-addressed directories above, so a running container cannot alter its
own code. The host builds are made by the same user that starts the containers; the content-hash check at start is what ties the
container to a specific build rather than to "whatever is at that path". The directory must not be writable by the container user
(it is mounted read-only; the host directory is mode 0555 after the build).

### f. Relation to item 23

If this holds, item 23 shrinks:

- still needed: step 2 (a deterministic base, built once), the manifest tool, `check-no-pyc`, and cross-host equivalence of the base
  (step 3), which is now one image instead of an inference and a shard image;
- no longer needed: reproducible C++ and pyc-free shard builds inside docker (`-ffile-prefix-map` in the image build, no ccache),
  the shard build itself, and most of the per-commit acceptance runs.

The determinism work moves to the host build, where it is cheaper to test (section g).

### g. Two hosts

The base image is built or loaded once and moved to the other host (it is the only large transfer, and it changes rarely). Each host
builds its own install tree at the same path with the same compiler version (the environment check covers `gcc`, `cmake`,
`python3`). The campaign compares `install_sha256` and `package_source_sha256` as it already does for images. If two builds of the same
commit differ, the content-manifest `diff` command names the files; the allowed exclusions are the ones in the content-identity
design, never inside the mounted tree. ccache is allowed on the host. When the two hashes differ, look in this order: (1) the compiler
and toolchain versions and the ccache version/config (`gcc`, `cmake`, `ccache -V`, `CCACHE_*`); (2) a cold build with `CCACHE_DISABLE=1`
on the host that differs; (3) the `content-manifest diff` file list. Where the build is not bit-identical (CPU-dependent flags, build
paths), the result is recorded, and the fix is a build flag, not an exclusion.

### h. Migration and tests

1. Add `capture --image` / `check --against-image` to `so101_env.py`, with fixture tests (fake `docker`, canned dpkg output).
2. Add the tree-hash command to the content manifest tool (reuses the existing walk), with tests for pyc rejection, mode, symlinks.
3. Build the base with the vendor file, entry script and corrected `.pth`; test the Dockerfile text like the other images.
4. A `start-mounted` script (the prototype in the run directory is the starting point) with the same container flags as today, plus
   the mounts, and a test that asserts the flag set.
5. Gate-style check on antzb: stack ready, reachability point, then a full short collection episode, against the image-based run.
6. Skew test: build against a host with one `ros-jazzy-*` package at another version and see whether section b refuses or whether the
   difference shows up as a runtime failure.
7. Only then: provenance and launch changes (section d), under approval, behind a switch that defaults to the current image path.

## Risks

- **ABI drift not caught by the check.** F5 shows the host and the base can differ in 208 packages and still run. A drift that matters
  and is not in the must-match set would surface as a crash or a silent numeric difference. Mitigation: the closure rule, the `ldd`
  rule, and step 6.
- **GPU and EGL.** The vendor file is needed (F3); driver userland comes from the NVIDIA runtime on each host and is the same
  concern as today.
- **Venv path.** Shebangs tie the host build to the venv path. A host without it fails at build time, which is early and visible.
- **pyc.** Python must not write bytecode on a read-only mount; `PYTHONDONTWRITEBYTECODE=1` is already set, and `python -I` calls need
  `-B` (the same defect was found in the image builds this session).
- **Mounted directories are campaign inputs (rule).** Under the AGENTS evidence rules the mounted `install` and `source` directories are recorded
  in the evidence root by path and sha256, and may not be deleted before the campaign that used them is sealed.
- **Build trees get deleted.** Old gate trees are cleaned up to keep disk free (the 50 GiB floor); mounted builds for a campaign must live in the
  commit-addressed directory and be kept until the campaign is sealed.
- **Reviewability.** A campaign record now names a base image ID and two tree hashes instead of one image ID; the qualification
  recompute (`collection_qualification_recompute.py`) must learn both.

## Decisions (coordinator, 2026-10-21)

1. The inference base is rebuilt without the old `so101_demo` in `/opt/venv`. No `rm` layer. The base images may not contain `so101_*`
   code; a test and a manifest check enforce it.
2. Same-path mounting at `/data/work/so101-build/mount/<commit12>/{install,source}` is the rule.
3. The must-match set is not a narrow set plus luck. Both hosts are aligned to the base image manifest with `so101_env apply`; must-match is
   all apt packages the host and image share, plus the closure and `ldd`-owner packages, plus the python minor version and venv pip set.
   Packages only the image has are judged by the closure. The skew test (step 6) stays, to show that the check refuses.
4. Step 7 (provenance, launch, config logic) is submitted for review only after steps 1 to 6 pass, behind a switch that defaults to off.
   It merges only after the coordinator has reviewed it.

Also: in the `python -I` audit, all four build-time call sites in the Dockerfiles carry `-B` (commit 6005d558d); the runtime
`ENTRYPOINT` uses `-I` on a read-only root, where no bytecode can be written.
