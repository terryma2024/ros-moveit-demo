# SO-101 ACT head and wrist RGB pipeline

This guide covers the ACT tooling that exists in this worktree: what each entry point does, which inputs
it refuses, and what has not been run yet. Everything described here was exercised by unit tests against
injected ports. Nothing here has driven a robot, a simulator or a GPU.

## What is implemented

The pipeline is built as a chain of small commands, each of which fails closed when an input is missing.

`act_sample` builds the split, collection and qualification manifests from a supplied candidate source.
It takes `--candidate-source`, `--reachability-report`, `--output`, `--collection-output`, `--seed`, and
optionally `--qualification-output` and `--qualification-load-output`. The candidate source is a closed
document holding `minimum_gap_m` plus the exact candidates of the five formal splits and the
qualification sets. The reachability report answers `verify` only for candidate identities it holds, after
checking all 14 gate results and their evidence hashes. The command writes nothing unless both inputs are
present and verify.

Manifests written this way carry a provenance sidecar recording
`NOT_FROZEN_UNTIL_RUNTIME_PREFLIGHT`. Until the runtime preflight produces the real candidate source and
reachability evidence, no manifest is frozen.

`act_collect` runs a single-scenario collection and `act_collect_parallel` a fixed-wave one. The parallel
command takes `--manifest`, `--calibration`, `--policy`, `--activation-receipt`, `--collection-config`,
`--runtime-config`, `--root`, `--worker-count`, and optionally `--split-manifest`,
`--qualification-contract` and `--resume`. Every refusal happens before a service exists, so a missing
input or an inadmissible manifest costs nothing. A qualification run must be given a contract path that
does not exist yet; the entry point creates it before anything can spawn, and refuses to reuse one.

`act_train` exports a dataset from the campaign index and runs one owned training job. It takes
`--manifest`, `--campaign-index`, `--gpu-binding`, `--config`, `--output` and `--device`. Training starts
only when the dependency lock is resolved, the exported dataset still hashes as recorded, the owner lease
is on CUDA, and the output path is free. The run always leaves a terminal state file, `COMPLETED` or
`FAILED` with the error, and a failure is re-raised rather than swallowed.

`act_offline_evaluate` scores a frozen bundle on the Offline Test split. It takes `--manifest`, `--bundle`,
`--freeze` and `--output`. It verifies the freeze first, requiring the six recorded digests and a sibling
`freeze-paths.json`, then re-hashes every file. It refuses a split with fewer than ten successful episodes,
refuses a cross-split chunk, resets the model per episode, and reports an episode-equal mean. Padded tail
frames are masked out of every joint metric.

`act_inference_worker` serves action prefixes for one session. It reads one request per line from
`--requests` and writes one reply per line to `--replies`, which must not already exist. It applies the
execution prefix frozen in the bundle, not the whole predicted chunk.

`act_session` composes a search-to-ACT session. It takes `--mode dry_run|plan_only|execute`, `--bundle`,
`--calibration`, `--policy`, `--activation-receipt`, `--runtime-config` and `--evidence-root`. The
planning modes need only an evidence root. `execute` requires every artifact and verifies the bundle and
runtime settings before submitting anything.

`act_evaluate` summarises one route on one split. It takes `--manifest`,
`--split rollout_validation|rollout_test|comparison`, `--bundle`, `--calibration`, `--runtime-config`,
`--root` and `--route act|moveit`, and writes a JSON report and a Markdown rendering, once each. The
end-to-end rate counts every attempted run, so a search failure stays in the denominator. When no run
locked, the locked rate is reported as null rather than as a perfect score.

## Contracts worth knowing before you change anything

A bundle document has a closed key set: `schema_version`, `kind`, `model_source`, `dataset_sha256`,
`config_sha256`, `policy_path`, `policy_sha256`, `normalization` and `action`. The policy must live inside
the bundle directory and its bytes must hash to `policy_sha256`. The normalisation block must record the
train split, because statistics drawn from validation or test would invalidate later comparisons. The
`action` block carries the frozen `chunk_size`, `execution_prefix`, `temporal_ensembling` and
`tail_padding_mask` that the runner applies.

`config/act/training.yaml` freezes the candidate smoke configuration: chunk size 10, execution prefix 1,
temporal ensembling off, and the tail padding mask on. A different value is a new contract rather than an
edit, and the loader says so with a named refusal.

`config/act/requirements.lock` ships deliberately unresolved. The versions can only be pinned by resolving
the selected LeRobot and PyTorch release inside a separate training interpreter, so a training run refuses
to start until the file says `RESOLVED` with a version and a source hash for every package.

## Running the tests

The focused tests for this surface run against the installed package in the worktree overlay. From the
package directory, with the test interpreter and the worktree overlay sourced:

```zsh
python -m pytest \
  test/test_act_bundle.py test/test_act_training.py test/test_act_training_config.py \
  test/test_act_training_requirements.py test/test_act_train_cli.py \
  test/test_act_offline_evaluation.py test/test_act_policy.py \
  test/test_act_inference_process.py test/test_act_inference_worker.py \
  test/test_act_session.py test/test_act_composition.py test/test_act_session_cli.py \
  test/test_act_evaluation.py -q
```

The parallel collection and gateway tests live in their own packages:

```zsh
python -m pytest test/test_act_parallel_collection.py test/test_act_parallel_collection_recovery.py \
  test/test_act_parallel_collection_runtime.py test/test_act_parallel_collection_integration.py \
  test/test_act_gpu_workload_client.py test/test_act_collection.py -q
```

On ai-station, point `TMPDIR`, `TMP` and `TEMP` at a fresh directory under the task's evidence root before
running pytest.

## What has not been run

No runtime has been started for this pipeline. The candidate source, the reachability evidence and the
qualification contract are supplied by the runtime ladder, so the manifests remain unfrozen. The
dependency lock is unresolved, so the LeRobot adapter that `act_train` and the inference worker load
through is not present in this worktree.

The ladder itself, in the order the plan gives it, is Task 8L to obtain a fresh `QUALIFIED` on the final
HEAD, then the W1 and W2 qualification runs, then the W8 qualification, then formal collection, training
and evaluation. None of those steps has been executed, and the formal accepted Train, Validation and
Offline Test counts are all zero.

The teleop HTTP endpoints, the generated TypeScript schema and the React panel that the plan lists for the
ACT panel are not implemented here either.
