# Stage bounds long enough for offline processing

Date: 2026-10-08

Trigger: the P3 switch moves the episode build after the Teacher. Measured on bag 147cb073: the processor takes 580 s (scan 14 s, replay 282 s, fresh QC 283 s). The frozen version-three runtime config gives the Worker's EXECUTING stage 240 s and `lease_duration_s` 300 s; the Teacher itself ends about 120 s after the stage begins. The ResultStore refuses a result completed after the lease deadline (`RESULT_AFTER_LEASE_DEADLINE`) and the Coordinator expires a worker past its stage deadline. With the frozen values the run cannot finish its own data.

Options considered:

1. Raise the frozen version-three values for every user. Rejected: it changes the W4/W8 campaigns and the macOS lanes that share the file.
2. A new runtime config file for the ACT collection, with version three accepting these two bounds as floors. Taken.
3. Run the processor after the commit and commit the Teacher result alone. Rejected: the ResultStore and the Coordinator would commit data that is not yet graded; the coordinator asked for the chain to work unchanged.
4. Speed the processor up five-fold. Not feasible: no single hot spot (profile `p3-prof.out`), the cost is spread over JSON parsing and per-record verification.

Recommended option taken under CP-3394: option 2.

## What changed

- `config/mujoco/parallel_batch_v3_act_offline.yaml` (new): the version-three file with `lease_duration_s: 1500.0` and `executing_hard_timeout_s: 1500.0`. Everything else is byte-identical (the diff is those two lines). `config/mujoco/parallel_batch_v3.yaml` is untouched.
- `parallel_batch/contracts.py`: version three pins every frozen value except these two, which are floors (`>= 300` and `>= 240`). Versions four to six keep the exact pins. The original file stays valid.
- `config/act/parallel_collection_v3.yaml` binds the new file (path and sha256). `act/first_episode_inputs.py` `RUNTIME_CONFIG_FILE` points to it, so a freeze prepares the inputs from it.

Why both bounds: the Coordinator renews the lease on every heartbeat to `min(now + lease_duration_s, stage deadline)`. With `lease_duration_s >= executing_hard_timeout_s` the deadline equals the stage deadline from the first renewal on and does not move. That is what lets the episode's audit lease (taken when processing starts) equal the lease the ResultStore compares at seal time, and appear among the EXECUTING lease values the commit-time check replays from the journal. With the old 300 s against a 240 s stage the same holds, but only because the stage is shorter than the lease.

Budget: Teacher about 120 s + processing about 600 s + seal about 5 s fits 1500 s. The processor is bounded to 1200 s by the orchestration. The FINALIZING stage (120 s) and the 10 s result acknowledgement are unchanged because the commit-time gate no longer repeats the QC recomputation (see the QC memo change doc).

## Tests

`test_p3_offline_switch.py`: the ACT file loads as version three with 1500/1500 and differs from the original in exactly those two fields; 239 s / 299 s are refused; version four stays pinned at 240/300; the collection config binds the file by sha256 and the input inspector reads it. `test_act_collection_config.py`, `test_act_first_episode_scope.py`, `test_parallel_batch_contracts.py` pass with the new path.

Rollback: `p3-base.tar.gz` (`contracts.py`, `parallel_collection_v3.yaml`), `p3-base3.tar.gz` (`first_episode_inputs.py`, the two test files); delete the new yaml.

Ledger CP: CP-3456.

## Rework (CP-3457): the Teacher bound is not a stage bound

The first version of this change raised `executing_hard_timeout_s` and said "everything else identical". The review found that this key is also the Teacher's own execution bound (the wait for the Teacher child, the Worker's `TEACHER_EXECUTION_DEADLINE` guard, the perception broker's RPC deadline, the pose wait). It was a silent relaxation of the Teacher's protection. The consumers now read a frozen Teacher bound of 240 s that no stage bound can raise (`contracts.teacher_execution_bound_s`); see `2026-10-08-teacher-bound-split-and-processing-budget`. The file still differs from the original in exactly two lines, `lease_duration_s` and `executing_hard_timeout_s`.
