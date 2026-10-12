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

`act_collect` runs a single-scenario collection.

`act_collect_parallel` admits and runs one container collection campaign. It first checks the arguments,
the contract for the chosen plane and every input file. It then freezes one input set, bound to the scene
list, in a new run directory under the registered evidence root. Everything that can be refused is refused
at this point, before anything is spawned. Next it asks unified admission for the GPU lease and the worker
slots. The owner starts the Teacher service once and one shard per slot per wave, and drives the scenes
through the Host-initiated container task control (four operations). The command releases the lease and
the slots only after every original container stop is proven. No real episode has been collected through
this command yet.

The required arguments are `--campaign-id`, `--run-id` (the name of the new run directory),
`--worker-count`, `--manifest`, `--source`, `--collection-config`, `--runtime-config`, `--campaign-config`,
`--input-candidates`, `--teacher-endpoint`, `--teacher-execution-policy`, `--episode-recorder-policy` and
`--runtime-policy`. The flag `--qualification` and the option `--qualification-report` select the plane.
The command reads `SO101_UNIFIED_EVIDENCE_ROOT`, `SO101_ACT_GPU_SELECTOR` and
`SO101_ACT_RESOURCE_BINDING_ID` from the environment.

There are two planes. With `--qualification`, `--worker-count` is 1 or 2 and `--manifest` is a functional
contract, or `--worker-count` is 8 and `--manifest` is the gate contract; in the eight-worker case
`--run-id` must equal the contract's `qualification_run_id`. Without `--qualification` the run is formal:
`--worker-count` must be 8, `--manifest` is the scene list, and `--qualification-report` is required. That
report must come from another run under the same registered evidence root, and formal admission recomputes
and verifies it in full. Passing `--qualification-report` together with `--qualification` is refused.

Exit code 0 means the campaign completed and settled, and the command prints one JSON line with
`campaign_id`, `run`, `plane`, `scene_count` and `waves`. Exit code 2 means the command refused before
admission. Exit code 1 covers everything after admission: an admission refusal, a run fault, an unproven
stop or a refused settle. When a stop cannot be proven, the command exits 1 with
`CAMPAIGN_CLEANUP_UNCONFIRMED` and leaves the lease and the worker slots held. The run directory's
`host/campaign-cleanup.json` records the stop result.

Two companion commands work on a finished exact-eight qualification run.
`act_build_parallel_qualification_report` takes `--contract`, `--campaign-root` and `--registered-root`,
recomputes the run from its originals and writes `host/qualification-report.json` in the run directory. It
creates the report once and never overwrites it, so a re-test needs a new run id. It exits 0 for a
`QUALIFIED` report, 3 when it wrote a `NOT_QUALIFIED` report, 2 when it refused and wrote nothing, and 1
for anything unexpected. `act_verify_parallel_qualification` takes `--report` and `--registered-root`,
recomputes the run, writes nothing and prints the proof as JSON. It also accepts `--campaign-config`,
`--source`, `--runtime-config`, `--collection-config` and `--contact-policy-fingerprint`, which must be
given all together or not at all; with them it also compares the report against the controlled identity
that formal admission uses. It exits 0 when the report is verified, 3 when verification is refused, 2 for
a usage or path refusal, and 1 for anything unexpected.

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
  test/act/test_act_bundle.py test/act/test_act_training.py test/act/test_act_training_config.py \
  test/act/test_act_training_requirements.py test/cli/test_act_train_cli.py \
  test/act/test_act_offline_evaluation.py test/act/test_act_policy.py \
  test/act/test_act_inference_process.py test/cli/test_act_inference_worker.py \
  test/act/test_act_session.py test/runtime/test_act_composition.py test/cli/test_act_session_cli.py \
  test/cli/test_act_evaluation.py -q
```

The parallel collection and gateway tests live in their own packages:

```zsh
python -m pytest test/act/test_act_parallel_collection.py test/act/test_act_parallel_collection_recovery.py \
  test/cli/test_container_task_campaign_integration.py test/cli/test_act_parallel_qualification_cli.py \
  test/adapters/act/test_act_gpu_workload_client.py test/act/test_act_collection.py -q
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
