# SO-101 evidence on its own partition — plan

Status: CONFIRMED by the human on 2026-10-18 ("在当前做到step结束后，实现上述的需求"). Execution starts after the current step: the
third_party gate fix, and the spot checks if they are running then. The directory layout rules are in AGENTS.md for both platforms
(`W=/data/work` on ai-station, `W=/opt/data/work` on macOS). AGENTS.md is mount-agnostic; how a machine backs the evidence
root, as this partition mount does, is machine setup and is recorded here and in the ledger only.

## Goal

Mount `/dev/nvme0n1p6` (488 GB ext4, UUID `247781db-7669-48d0-8284-3a718743e559`, shrunk from Windows, empty) at
`/data/work/so101-evidence`. Only evidence stays on it. Environments, build products, tools, exported datasets and trained
policies move to the large root disk under `/data/work/`. The mount path is the current path, so every absolute path in the
ledger, manifests and seal records stays valid.

## Human decisions (2026-10-18)

- The partition has no content and may be used.
- Old history is deleted, conclusion files kept (batch e, `R/evidence-deletion-20261018e`): experiments/, head-interrupt-fix,
  occlusion-dedup, centering-convergence, act-native, act-w1, act-w2. About 227 GiB deleted. Live tool dependencies are kept
  whole (`experiments/nonhead-installed-freeze.3SxS0GQW`, `centering-convergence-20261012/scripts`).

## What stays in evidence

- The sealed roots (`REG/SEALED-ROOTS.json`, 15 roots, about 160 GB, including the sealed gates and image build contexts).
- `REG/handoffs/teacher-act-decoupling-20261005.1RmsJ3ZJ` (r11/r12 contact calibration and spot-check evidence).
- Calibration, diagnostics, run logs, campaign run roots, gate results, ledger-cited result files, deletion records.
- The test scratch (`R/scratch`, per-run TMPDIR): AGENTS.md requires it under the durable evidence root. It is cleaned regularly.
- Future collection runs (rig v2 EXP-623/624/625, about 150 GB).

## What moves out (new homes on the root disk)

| Content | From | To | Evidence keeps |
| --- | --- | --- | --- |
| Python environments | `REG/train-venv`, `REG/test-venv` | `/data/work/venvs/so101-act-train`, `/data/work/venvs/so101-act-test` | path and `pip freeze` in the ledger |
| Pretrained weights | `REG/models` | `/data/work/models/` | sha256 list |
| Exported datasets (LeRobot) | `train-run-*/bundle.dataset` | `/data/work/so101-datasets/<name>/` | export manifest and sha256 |
| Trained policies | `train-run-*/bundle` | `/data/work/so101-policies/<train-run>/` | training logs, metrics, bundle sha256 |
| Gate build and install trees (unsealed gates) | `R/gates/<id>/{build,install,log}` | `/data/work/so101-build/gates/<id>/` | `gates-result.txt`, rc, timing, JUnit, decisions |
| Gate tooling, ccache, pytest plugin, Claude tools | `R/fast-gate`, `REG/handoffs/claude-tools-20261016` | `/data/work/so101-tools/` (later: git `scripts/`) | none |
| Superseded image build contexts (unsealed) | `R/image-build-*` | deleted when the image is superseded (reproducible from git) | image digests in the ledger |

No symlink from evidence to outside: the seal guard resolves real paths.

## Steps

1. Tooling (Sonnet writer, Opus review):
   - The gate scripts take a build root (`/data/work/so101-build/gates/<id>`) separate from the result directory in evidence; the
     install used by templates is read from the build root.
   - The training tools write datasets and policies to the new roots and record path plus sha256 in the run directory.
   - Template env files, `build_images.zsh` and the gate scripts get the new tool and venv paths.
   - AGENTS.md and README notes for the new layout.
   - Proof: a v2 (or the fixed v3) Host gate run in the new layout, the template `--check-only` runs, a training gate dry run.
2. Move the non-evidence content to the root disk (copy, verify sha256 or `rsync -c`, then delete the source); re-run the step 1 proofs.
3. Copy evidence to the partition on a quiet host (no campaign, gate or training):
   - `sudo mkdir /mnt/so101-ev-new && sudo mount /dev/nvme0n1p6 /mnt/so101-ev-new`
   - `sudo rsync -aHAX --numeric-ids /data/work/so101-evidence/ /mnt/so101-ev-new/`
   - Verify: file count and byte totals per top-level directory; a full manifest readback of every sealed root (sha256 per file).
4. Switch:
   - `sudo umount /mnt/so101-ev-new`; `sudo mv /data/work/so101-evidence /data/work/so101-evidence.pre-mount`;
     `sudo mkdir /data/work/so101-evidence`
   - fstab: `UUID=247781db-7669-48d0-8284-3a718743e559 /data/work/so101-evidence ext4 defaults,noatime 0 2`;
     `sudo mount -a`; ownership `matianyi:matianyi` on the mount root
   - Verify again (sealed readback, write test under the TMPDIR rule), then resume work.
5. `/data/work/so101-evidence.pre-mount` is kept until the human authorises its deletion.

The sudo commands are run by the human (`! <command>`); the agent prepares and verifies.

## Timing

Step 1 is code work. Steps 3–4 need a window with no runs, about 30–60 minutes for about 230 GB plus the readback. Best window:
after the third_party gate fix lands and before the spot checks resume.
