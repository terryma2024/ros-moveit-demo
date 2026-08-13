# SO-101 Gazebo Python Capability Evidence

This checkpoint records the terminal live acceptance for the package-owned Gazebo
Planning Scene, camera, and transactional Reset capabilities. The authoritative
experiment history is
`docs/experiments/so101-gazebo-python-capabilities-experiment-ledger.md`; raw artifacts
remain under `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live`.

## Fixed contracts

- Owner package: `so101_demo_py`
- Public CLIs: `scene_setup`, `camera_preset`, `teleop_reset`
- Frozen MuJoCo policy SHA-256:
  `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`
- Geometry manifest SHA-256:
  `6dc64c197a82316c4ac856530c6caf5d905ffd2b0ea2778d85d87b9a3e89b235`
- Primitive counts: table `1`, pedestal `1`, plastic cup `13`

## Terminal live results

- `CP-GZPY-SCENE-002`: `VALID/SUCCEEDED`. Manifest-derived scene apply and independent
  read-back proved exact membership, attachment state, pose/color/geometry, and
  primitive counts. Scene receipt SHA-256 is
  `c256a061d1cb56e67e4dc5164d264c486d24722e7d10e95b9342adfc738624ae`;
  independent raw read-back SHA-256 is
  `e917804579fa88b51bf88853f39dffaca7a648d0197513170afef752aac84ad4`.
- `CP-GZPY-CAMERA-001`: `VALID/SUCCEEDED`. The package-owned `top` preset called
  `/gui/move_to/pose`, received `data: true`, and produced inspected fresh before/after
  CUA snapshots. Receipt SHA-256 is
  `29b604bed0f81db65e01db1e9691ba61c22e3924b20a95bc63099a71745a4b48`.
- `CP-GZPY-RESET-005`: `VALID/SUCCEEDED`. A fresh independently proven arm/cup
  disturbance was followed by a zero-exit thirteen-phase transaction. Independent
  native Gazebo pose/ECS, raw MoveIt scene, controller, joints/velocities, TF, and
  inspected visual evidence all converged. Reset receipt SHA-256 is
  `1eaf7533cf811ed34f93dfc6117af3b97e50106993a2b13ee29aefa374a0423b`.

## Inspected screenshots

- Camera overview before:
  `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/camera-001/cua-before-overview.png`
  (`d147aff37abba509a2a6a1a7f6d3207843febbdd3f51f2c4096c9527c3e1d730`)
- Camera top after:
  `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/camera-001/cua-after-top.png`
  (`631bf5d93d9eec90069c21d74a2b4a649093b509ab1b10be50ab53b6bd4882f6`)
- Reset disturbed before:
  `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/reset-005/gui-disturbed-fallback/20260813T122142-2c279c838b8a/desktop.png`
  (`3f09ca90bcd719c89bbe5787737a51b53b8c0a82eb8c6cce5d80a06a3f726576`)
- Reset converged after:
  `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/reset-005/gui-final-fallback/20260813T122713-02e1b84358e8/desktop.png`
  (`b419ee89fbdfc017e8ec7f7300d0eab959c1a38d8428cb66a147e1eaea14d00d`)

## Final fixed-bundle MuJoCo qualification

The behavior source commit
`213ac0da3b4f2a756c2c4e66e8e6c28af9e2168a`, fresh installed prefix
`/tmp/so101-debug-gazebo-python-capabilities-boWK6J/final-candidate-005-install/so101_demo_py`,
bundle `438f968141ff3b3999799b8dc06d36c386950eed335a82e314a2fe2e050119dd`,
and frozen policy were identical across five consecutive independently started and
stopped FULL_RESTART experiments:

- `cp-gzpy-fr-021-01` — manifest SHA-256
  `25dd6a49bebdb6b87729ce1b707f8c65562ecf32f3c781696900d29e0477464a`
- `cp-gzpy-fr-022-01` — manifest SHA-256
  `fc3e1a12c19679dd63f1d839a8af1e6cec16a4e90780135a2fae4b93adecfc17`
- `cp-gzpy-fr-023-01` — manifest SHA-256
  `0da61cc8b4c16e79691b4e7a69078e679a6c93fa8cd676b50300954313bb8fa5`
- `cp-gzpy-fr-024-01` — manifest SHA-256
  `b14c9338998a27d6e09848757ac0956bc3602a048afe3a11f0d4440f012f2766`
- `cp-gzpy-fr-025-01` — manifest SHA-256
  `ddfaf9e9df89308d9441ac4a87ff8b0961f61fcdcae606be4c5c015e27276246`

Each independently returned `QUALIFIED` under `verify-batch`, reset at epoch `1`, ran
all nine production phases, proved successful physical placement with no primary
failure, closed gap-free lossless transport evidence as
`COMPLETE/PHYSICAL_TRANSPORT_SUCCESS`, and performed ordered clean shutdown. Earlier
invalid batches are retained in the ledger and do not contribute to this streak.
