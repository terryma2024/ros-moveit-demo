# so101-env: align a host to a reference environment

`scripts/env/so101_env.py` records one Ubuntu host's runtime environment in a manifest and brings
other hosts of the same LTS release to the same state. It uses only the Python 3.12 standard
library, so it runs on a bare host.

The reference host is ai-station. Other hosts are aligned to it, then both are locked.

## Commands

```bash
# On the reference host (read-only apart from the files it writes)
python3 scripts/env/so101_env.py capture --output env-manifest.json --log capture.jsonl \
  --export-wheels wheels/ --export-tools so101-tools.tar.gz

# On any host: compare with a manifest. Exit code 1 if a "must match" item differs.
python3 scripts/env/so101_env.py check --manifest env-manifest.json --json rows.json

# On the target host (uses sudo for apt only). Copy manifest, wheels/ and the tarball over first.
python3 scripts/env/so101_env.py apply --manifest env-manifest.json \
  --wheels wheels/ --tools-tar so101-tools.tar.gz --log apply.jsonl [--snapshot-date YYYY-MM-DD]

# On the reference host: hold every manifest package at its current version
python3 scripts/env/so101_env.py lock --manifest env-manifest.json
```

Pass `--dry-run` to `apply` to print the plan without changing anything. Pass `--work-root` if the
venvs and `so101-tools` do not live under `/data/work`. Pass `--no-rosdep` to `capture` on a host
without a rosdep database.

## What the manifest covers

| Item | Source |
| --- | --- |
| OS release and LTS codename, kernel | `/etc/os-release`, `uname -r` |
| NVIDIA driver, GPU model and UUID | `nvidia-smi` |
| apt sources | `/etc/apt/sources.list.d/*`, `/etc/apt/sources.list` |
| apt packages with exact versions | see below |
| `python3` version | `/usr/bin/python3 --version` |
| Every venv under `<work-root>/venvs` | interpreter, `pip freeze --all --local`, freeze sha256, torch and CUDA versions |
| `<work-root>/so101-tools` | sha256 of every file and the target of every symlink (`__pycache__` and `.pyc` skipped) |
| docker | `docker --version` |

The apt package list is the union of:

- every installed `ros-jazzy-*` package;
- the `package.xml` dependencies under `src/` (all `depend` tags), resolved with
  `rosdep resolve --rosdistro jazzy --os ubuntu:noble`, limited to packages that are installed;
- the Gazebo Harmonic packages from packages.osrfoundation.org, matched by the prefixes `gz-`,
  `libgz-`, `python3-gz-`, `libsdformat` and `sdformat`;
- the fixed list `EXTRA_APT` in the script, taken from the install lines in the docs and
  Dockerfiles (build tools, `rsync`, `tmux`, EGL and X11 libraries, `docker.io`, and similar).

Keys that rosdep cannot resolve are recorded under `apt_scope.rosdep_keys_unresolved`. Packages the
manifest does not name are never touched. Extra `ros-jazzy-*` packages on the target are reported.

Not covered: the NVIDIA kernel driver itself, the kernel, docker images, Python packages installed
outside the venvs, and apt packages that no rule above selects.

## Comparison classes

| Class | Items | Effect |
| --- | --- | --- |
| must match | LTS codename, python3 minor version, every manifest apt package version, venv Python minor version and `pip freeze`, `so101-tools` hashes | `check` exits 1 |
| should match | OS point release, NVIDIA driver, docker version, python3 patch version, torch and CUDA string, extra `ros-jazzy-*` packages, venvs not in the manifest | warning only |
| host-specific | kernel, GPU model and UUID, CPU, memory, apt source files | reported only |

Versions are compared with Debian rules (epoch, `~`, letters, build dates), so `check` can say
whether the host is newer or older than the manifest.

## What `apply` does

1. Refuses if the LTS codename or the Python minor version differs.
2. Compares apt versions. A version that no configured source offers stops the run unless
   `--snapshot-date` (or `ros_snapshot.date` in the manifest) is given. In that case it writes
   `/etc/apt/sources.list.d/so101-ros-snapshot.list` with the dated `snapshots.ros.org` source, runs
   `apt-get update`, and stops if the versions are still missing.
3. Simulates `apt-get install pkg=version ...`. If apt would remove packages it stops; pass
   `--allow-remove` to accept that.
4. Installs with `--allow-downgrades --allow-change-held-packages`, then `apt-mark hold` on every
   manifest package.
5. Rebuilds every venv whose freeze differs. The old venv is moved to `<name>.pre-align-<stamp>`,
   a new one is created with `python3 -m venv --without-pip`, and the exact wheels are installed
   with `pip install --no-deps --no-index --find-links`. Wheel hashes are verified first.
6. Replaces `so101-tools` from the tarball. The old tree is moved to `so101-tools.pre-align-<stamp>`.
7. Runs `check`. The exit code of `apply` is the exit code of that final check.

Nothing is deleted. Moved-aside trees are deletion candidates once the result is confirmed. Every
step is written as JSON lines to `--log`.

## Aligning a second host

1. If the target has a newer version of any package than the reference, upgrade the reference to
   it first and run the gates there. The reference is the single source of truth.
2. `capture` on the reference with `--export-wheels` and `--export-tools`.
3. Copy the manifest, `wheels/`, the tarball and this script to the target. A target that cannot
   reach the reference over ssh needs the copy pushed from the reference.
4. `apply`, then `check` (the last step of `apply`), then `lock` on the reference.
5. To change the environment later, `apt-mark unhold` the packages, change the reference, and
   capture and apply again.

## Tests

`scripts/tests/test_so101_env.py` covers version comparison, diff classification, apply planning
and the parsers with fixture manifests. It does not call apt.

## GL / EGL

The MuJoCo camera plugin (C++) tries GLFW and falls back to a surfaceless EGL
context; `mujoco.Renderer` needs `MUJOCO_GL=egl` (the gate scripts export it).
The manifest therefore records:

- the Mesa and glvnd apt packages (`libegl*`, `libgl1*`, `libglvnd*`, `libgles*`,
  `libgbm*`, `libosmesa*`), which `apply` aligns with the rest of apt;
- the `/usr/share/glvnd/egl_vendor.d/*.json` files by sha256 (a missing file is a
  must-match difference, a content difference is a warning);
- the NVIDIA GL userland versions (`libnvidia-gl-*`, `nvidia-driver-*`), reported as
  warnings only because they are tied to the kernel module and need a driver
  upgrade and reboot, which `apply` never does.

`check` also runs a functional probe: a 64x64 headless render with the
`so101-act-test` venv python, `MUJOCO_GL=egl` and no `DISPLAY`. A failing probe is a
must-match difference (`gl.probe`). Use `--no-gl-probe` to skip it.

## Apt mirror

`capture` stores the full text of every apt source file in the manifest
(`apt_sources`), so the effective ROS mirror is part of the reference. A host that
pulls from a slow upstream can run `apply --use-reference-sources`: the ROS and
Gazebo source files that differ are replaced by the reference text (the old file is
kept as `<name>.pre-align-<stamp>`), then `apt-get update` runs before planning.
