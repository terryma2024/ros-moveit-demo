# SO-101 MuJoCo FULL_RESTART five-run baseline

## Purpose

This document summarizes the immutable, read-only baseline generated from `EXP-126` through
`EXP-130`. It is the comparison reference for the next RESET_WORLD batch. It does not derive or
change any motion target, controller setting, contact threshold, or success criterion.

Canonical artifacts:

- `so101-mujoco-full-restart-baseline.json`
- `so101-mujoco-full-restart-baseline.sha256`
- JSON SHA-256: `7e24e479dbed11292b7e95e95069a29a18e610298f5d9d655cbf64dad3f66368`

## Evidence identity

- Lifecycle: `FULL_RESTART`
- Independent experiment units: `5`
- Experiments: `EXP-126`, `EXP-127`, `EXP-128`, `EXP-129`, `EXP-130`
- Raw transport samples: `18,575`
- Physics timestep: `0.002 s`
- Lossless runs: `5/5`
- Runtime source commit: `d30bf2bd54ea9359d08b866cdda447dfe2a3c271`
- Motion-policy SHA-256: `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`
- Contact-policy SHA-256: `c4ba607fea92f7c605fbc8cf08df0dfa3278113c71d1dd6ff10ea402e8186f82`
- EXP-126 visual evidence: `USER_WAIVER`; its physical, controller, manifest, and lossless raw
  evidence remain included.

Every result, owner manifest, phase artifact, run index, and content-addressed chunk is rehashed
before it contributes to the baseline. Sessions, reset epochs, chunk sequences, physics steps, and
simulation times must be continuous and agree with their result summaries.

## Independent-run statistics

All values below are computed across the five independent runs.

| Metric | Min | P50 | P95 | Max |
|---|---:|---:|---:|---:|
| Contact-hold phase maximum force (N) | 0.600895 | 0.603557 | 0.607257 | 0.607548 |
| Transport phase observer maximum force (N) | 4.913286 | 4.925252 | 4.979617 | 4.982987 |
| 500 Hz transport single-contact peak (N) | 6.565566 | 6.605648 | 6.609787 | 6.610767 |
| Descend phase maximum force (N) | 4.773448 | 4.783932 | 4.816751 | 4.823626 |
| Place-alignment phase maximum force (N) | 4.497178 | 4.727048 | 5.428472 | 5.496411 |
| Released static final force (N) | 0.151060 | 0.233202 | 0.239174 | 0.240023 |
| Final X (m) | -0.080126 | -0.078973 | -0.078291 | -0.078169 |
| Final Y (m) | -0.248172 | -0.247836 | -0.247035 | -0.246911 |
| Final Z (m) | 0.164726 | 0.165262 | 0.165456 | 0.165492 |
| Final upright tilt (rad) | 0.002017 | 0.015663 | 0.017348 | 0.017432 |

## Repeated-measure diagnostics

The 18,575 physics-step samples are repeated measurements inside five runs, not 18,575 independent
experiments. They are suitable for waveform and drift comparison only.

| 500 Hz metric | Min | P50 | P95 | P99 | Max |
|---|---:|---:|---:|---:|---:|
| Global maximum single-contact force (N) | 0.759984 | 4.094265 | 6.197460 | 6.575667 | 6.610767 |
| Linear speed (m/s) | 0.00000044 | 0.012346 | 0.030716 | 0.032856 | 0.033295 |
| Angular speed (rad/s) | 0.00000025 | 0.041119 | 0.086364 | 0.089402 | 0.092418 |
| Left fingertip compression (m) | 0.00002364 | 0.00037965 | 0.00049562 | 0.00051244 | 0.00051397 |
| Right fingertip compression (m) | 0.00008590 | 0.00030860 | 0.00042166 | 0.00044245 | 0.00044399 |

The per-fingertip total normal forces can reach about `16 N` because they sum several simultaneous
contacts. The dynamic hard-stop metric is the global maximum **single-contact** force, whose observed
five-run maximum is `6.610767 N`. These quantities must not be substituted for one another.

## Interpretation contract

- `policy_effect` is `NONE_READ_ONLY_BASELINE`.
- `threshold_derivation` is `NONE_DIAGNOSTIC_COMPARISON_ONLY`.
- RESET_WORLD results must remain a separate lifecycle batch.
- A RESET_WORLD observation outside this baseline is a diagnostic signal, not automatic permission
  to change the already successful strategy or its thresholds.
- Any future baseline comparison must first match the runtime fingerprint and prove raw evidence
  continuity.

## Reproduction

From the worktree root on ai-station:

```zsh
PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
  PYTHONPATH=src/so101_mujoco_demo_py \
  python3 src/so101_mujoco_demo_py/scripts/summarize_full_restart_baseline.py \
  --evidence-root /data/work/so101-evidence/maintainability/so101-debug-mujoco-maintainability-remediation \
  --experiment EXP-126 --experiment EXP-127 --experiment EXP-128 \
  --experiment EXP-129 --experiment EXP-130 \
  --visual-waiver EXP-126 \
  --output docs/experiments/so101-mujoco-full-restart-baseline.json \
  --sha256-output docs/experiments/so101-mujoco-full-restart-baseline.sha256

cd docs/experiments
sha256sum -c so101-mujoco-full-restart-baseline.sha256
```
