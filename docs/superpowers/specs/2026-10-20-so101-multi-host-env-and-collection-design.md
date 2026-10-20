# SO-101 ACT: one-command host environment alignment and two-host collection with merge — design and plan

Status: DRAFT, waiting for the human's confirmation.

## Human request (2026-10-20)

"让antzb的 ros 和 python 的版本和本机保持一致（沉淀一个脚本，可以在任意一台ubuntu，只要ubuntu的LTS版本一致，就可以一键对齐运行环境版本）。后续我想让antzb和ai-station能同时进行数据采集（各分摊一部分采集任务，完成后合并），采集能力要能支持合并数据的功能。"

## Facts (2026-10-20)

| | ai-station | antzb |
| --- | --- | --- |
| OS | Ubuntu 24.04 (noble) | Ubuntu 24.04.4 (noble) |
| GPU / driver | RTX 5060 Ti, 595.99.02 | RTX 5080, 595.84 |
| ROS apt source | `mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu` (latest builds only) | (to check) |
| ros-jazzy packages | 500, September/October builds (rclpy 7.1.12, controller-manager 4.48.1) | 509, mostly June builds (rclpy 7.1.11, controller-manager 4.45.2); 395 of 500 differ in build date |
| Python | 3.12.3 | 3.12.3 |
| venvs | `so101-act-train`, `so101-act-test`, `so101-grounded-sam` | `so101-grounded-sam`, `so101-act-train-profile`, `so101-v5-t004-perception` |
| Docker | collection images built locally (campaign shard / inference) | 27 older `so101*` images |

- The containers carry their own pinned ROS set (CP-3725/3726), so collection results depend on the images, not on the host apt set.
- The host ROS set matters for the Host gate, for the native rollout stack and for the Host CLI.
- The ROS mirror keeps only the newest build of each package. Exact old versions cannot be installed from it. ROS publishes dated snapshots (`snapshots.ros.org/jazzy/<date>/`), and those can.

## Part A: `so101-env` — capture and apply a host environment manifest

A tool under `scripts/env/` (tracked in git) with three commands:

1. **`capture`** (on the reference host) writes `env-manifest.json`. The manifest holds:
   - the OS release and LTS codename;
   - the kernel and the NVIDIA driver;
   - the apt sources;
   - every `ros-jazzy-*` package and every apt package the repo needs, with exact versions (the list comes from `package.xml` and the build and gate docs);
   - `python3 --version`;
   - for every venv under `W/venvs`: its interpreter, `pip freeze --all` and a hash of the freeze;
   - the CUDA and torch versions reported by each venv;
   - the `W/so101-tools` file hashes;
   - the docker version.
2. **`check`** (on any host) compares the host with a manifest and prints a diff table. It exits non-zero on any difference in a class marked "must match". The classes are:

   | Class | What it covers | How differences are handled |
   | --- | --- | --- |
   | must match | OS LTS codename, ROS apt package versions, Python minor version, venv pip freezes, `so101-tools` hashes | `check` fails |
   | should match | NVIDIA driver, docker | warnings only |
   | host-specific, never compared | GPU UUID and model, CPU, memory | reported only |
3. **`apply`** (on the target host, sudo) makes the target match the manifest:
   - **Refuses** if the LTS codename differs.
   - **apt:** installs the exact versions (`apt-get install pkg=version`) from the configured repo. If a version is missing there, it adds a ROS snapshot source whose date carries those versions, and the manifest records which snapshot. Installed packages are then held (`apt-mark hold`). Packages not in the manifest are left alone, except that extra `ros-jazzy-*` packages are listed.
   - **venvs:** created at the same paths with `pip install --no-deps -r freeze`. Wheels come from a wheel cache the reference host exports (`capture --export-wheels`), so the result is byte-exact without network differences.
   - **so101-tools:** rsync from the reference host.
   - Ends with `check`, which must pass.
   - Every action is logged to the evidence root.

**Recommended alignment for antzb now:**
- Upgrade **both** hosts to one ROS snapshot date. ai-station's current set (built 2026-09/10) is not exactly reproducible from the "latest only" mirror, and pinning both to a snapshot makes the result reproducible on any noble host.
- Then capture the manifest on ai-station and apply it on antzb.
- The ai-station upgrade changes the host ROS set, so the next Host gate re-runs the upstream ros2_control and JTC suites (the apt-hash rule). A new image build is needed only if we want the image base to follow, and that is optional.
- **Side effect:** another user's teleop web service (port 8000) runs on antzb. It is restarted after the upgrade, after its owner is told.

## Part B: two-host collection with merge

**Goal:** split one formal scene list between ai-station and antzb, collect at the same time, and merge into one sealed dataset that export and training treat like a single campaign.

**Design:**
1. **One frozen input set, one scene list, a deterministic split.** The authoring step takes the full list and a host assignment. The assignment is a stable function of the scene_id, with shares set by host throughput, for example 40 % ai-station and 60 % antzb. The assignment file is frozen into each host's inputs.
2. **Same identity on both hosts:** the same commit, the same images (digest-identical; built once and copied with `docker save`/`load`, the digests checked), the same configs and frozen policies, and the same contact-policy activation.
   - `gpu_uuid` is in today's controlled identity. With two GPUs, identities would differ.
   - Recommended: per the confirmed logic/runtime design, move `gpu_uuid` to the environment class (recorded, not compared). Record the GPU model, and require the qualification envelope per GPU model (see 3).
3. **Qualification.** Each host runs its own qualification on the same contract. Different GPU and CPU mean a different load profile, and the RO envelope is per host. Both must be QUALIFIED. Each host's formal run is admitted only with its own qualification report.
4. **Run.** Each host runs its formal campaign on its subset of the list, with its own retry rounds, finalize and seal. The stage-by-stage collection (item 1) applies on each host.
5. **Transfer.** antzb's sealed run root (plus inputs, qualification run and report) is rsynced to the ai-station evidence partition and re-verified there: a sealed readback, 0 problems required. The sealed bytes are unchanged and the transfer is logged.
6. **Merge.** A tracked `act_merge_collections` CLI replaces the evidence-side `merge_indexes.py`. It takes N sealed indexes and writes one merged index plus a manifest. It refuses if:
   - any controlled identity differs (environment class excluded);
   - the scene sets overlap;
   - the union does not equal the formal list;
   - a source is not sealed or fails readback.

   Each committed episode keeps its own `collection_evidence` pointing at its original run root. The merged index records every source (path, sha256, host, GPU, qualification report sha).
7. **Export and training** read the merged index unchanged (`resolve_committed_episodes` already works on per-entry evidence). This has been proven before with merged-v2: EXP-620 + EXP-622.

## Implementation plan (after confirmation; Sonnet writers, Opus review; tests first, fixtures only)

1. Part A tool (`capture` / `check` / `apply`) with unit tests for the manifest diff and the apply planning, using fixture manifests and no real apt. Run `capture` and `check` on both hosts.
2. Align (needs the human's go-ahead for the sudo steps on both hosts):
   - pick the snapshot date;
   - apply on ai-station, run the Host gate with `--full`;
   - capture;
   - apply on antzb, run `check` (must pass), run the antzb Host gate.
3. Part B, in this order:
   - the host assignment in authoring;
   - `gpu_uuid` → environment class (with item 1);
   - `act_merge_collections` with refusals and tests;
   - image transfer with digest checks;
   - transfer and readback;
   - an end-to-end dry run with two small debug campaigns (8 scenes each), merged, exported and trained for a few hundred steps.
4. Then the boundary search, sampling, two-host qualification and formal collection (the boundary-sampling design).

## Decisions (recommended answers)

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Align to a ROS snapshot date (both hosts), or upgrade both to "latest" now and pin that? | A snapshot date: reproducible on any noble host |
| Q2 | Restart the teleop service on antzb during the upgrade | Yes, after notifying its owner |
| Q3 | `gpu_uuid` out of the controlled identity (environment class) | Yes, with per-host qualification |
| Q4 | Host share | By measured scenes/hour, initially 40 % ai-station / 60 % antzb |
| Q5 | Merge tool tracked in git (`act_merge_collections`) | Yes, replacing the evidence-side script |
