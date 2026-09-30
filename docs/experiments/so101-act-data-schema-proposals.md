# Schema proposals awaiting owner ratification (Task 3)

These two schemas are **proposals, not adopted contracts**. The Task 3 reviewer ruled that the exact
source-derived raw-frame schema and the window schema must be ratified by the owner before the
boundaries change together, and that the absence of frozen key names does not justify accepting missing
facts. Until they are ratified the writer records the caller's window verbatim and the raw-frame group
stays optional-but-validated at every boundary, while the formal epilogue refuses to seal without
coverage.

Each proposal states the fields, their types, the ordering rules, and exactly which boundary changes
when it is ratified. Nothing here is implemented beyond what the "current state" column says.

## Proposal A — raw controller reference frames (`references.jsonl`)

Reviewer constraints folded in: separate `arm` and `gripper` frames (never fuse two publication/receipt
clocks into one purported raw frame); each frame keeps its **ordered** `joint_names`, **positions as well
as velocities**, the source stamp, the receipt stamp and the observer's own identity/sequence; the
registered source has **5 arm joints and 1 gripper joint**, so the outer six-dimensional projected
reference needs an **explicit checked mapping**; distinguish an original publication from a reference
**evaluated at a requested future instant**, and bind that evaluation to accepted-goal identity/interval
plus revoke/stop history; preserve the history at the producer boundary rather than only the latest
bounded cache/query snapshot; carry the group losslessly through port, tap, capture, writer and verifier.

| Field | Type | Meaning |
| --- | --- | --- |
| `frames` | object keyed `arm`, `gripper` | one entry per controller frame; both keys required together |
| `frames[kind].joint_names` | list of non-empty strings | ordered names exactly as the observer validated them (5 for `arm`, 1 for `gripper`) |
| `frames[kind].positions` | list of finite numbers | same length and order as `joint_names` |
| `frames[kind].velocities` | list of finite numbers | same length and order as `joint_names` |
| `frames[kind].sim_stamp_ns` | integer ≥ 1 | the source's own sim timestamp |
| `frames[kind].received_monotonic_ns` | integer ≥ 1 | the observer's receipt instant |
| `frames[kind].observer_sequence` | integer ≥ 1 | the observer's own per-kind publish sequence |
| `evaluation` | object | what the projected six-dimensional record describes |
| `evaluation.requested_sim_time_s` | finite number ≥ 0 | the instant the reference was evaluated **for** |
| `evaluation.basis` | `published` or `interval` | whether it came from a publication or a proven accepted interval |
| `evaluation.goal_id` | non-empty string or `null` | the accepted goal the interval belongs to; required when `basis == "interval"` |
| `evaluation.accepted_sim_s` | finite number ≥ 0 or `null` | the acceptance stamp of that goal; required with `goal_id` |
| `evaluation.revoked_sim_s` | finite number ≥ 0 or `null` | set when a later revocation or stop applied to that goal |
| `projected_positions` | list of 6 finite numbers | the outer action the label uses |
| `projection_map` | list of 6 `[kind, index]` pairs | the checked mapping from the six dimensions to `frames[kind].positions[index]`; `arm` supplies 0–4 and `gripper` 5 |

Group rule: all fields above are all-or-nothing per reference record. Ordering rules: per `kind`,
`observer_sequence` and `sim_stamp_ns` increase strictly and `received_monotonic_ns` never decreases;
`evaluation.requested_sim_time_s` is the reference's target instant, not its publication instant, and
`basis == "interval"` requires `goal_id` **and** `accepted_sim_s` with the target inside
`[accepted_sim_s, revoked_sim_s or ∞)`. A revocation recorded later for that goal voids the record the
same way the audit already voids an accepted reference for its instant.

Boundaries that change together when ratified: `adapters/act/controller_reference_observer.py` (already
holds the per-kind frames), `adapters/act/ros_broker.py::reference_state` (must expose `frames` and
`evaluation` per kind instead of a fused six-joint projection), `adapters/act/ros_expert.py` (pass-through
only), `act/expert.py` (forward instead of projecting), `act/continuous_capture.py` (forward),
`act/episode_audit.py` (closed schema, group rule, readback parity), and the recorder correlation if the
projected action must match `projection_map`.

Current state: the audit accepts the flat four-field group (`joint_names`, `sim_stamp_ns`,
`received_monotonic_ns`, `velocities`) under an all-or-none rule, the tap and capture forward it, the port
passes anything through, and **the broker still projects** — so no production run supplies it.

## Proposal B — collection window (`audit-manifest.json.window`)

Reviewer constraints folded in: `collection_start <= observed first command <= physics end <= collection
end` for a **complete executed case**; `first_command <= label_cutoff` is **not** justified for
early-failure or pre-command captures; the last labelled observation is bounded independently by
`collection_start`/`physics_end`, and its `t + 0.1` reference target must be physically covered; the
cutoff is related to actual rows and the source schedule rather than to ordered numbers; cadence,
required streams, coverage/count/ranges and permitted gaps come from the frozen inputs plus observed
history; no-command/no-label or interrupted diagnostic evidence is represented explicitly instead of
inventing timestamps.

| Field | Type | Meaning |
| --- | --- | --- |
| `source_schedule` | object keyed by stream name | each value a list of non-negative finite instants actually **observed**, per stream |
| `streams_required` | list of non-empty strings | streams the frozen inputs require for this mode |
| `cadence_s` | finite number > 0 | the expected source cadence, from the frozen inputs |
| `permitted_gaps_s` | list of `[start_s, end_s]` pairs | gaps the frozen inputs allow, e.g. a documented pause |
| `collection_start_s` | finite number ≥ 0 | first source instant of the episode |
| `collection_end_s` | finite number ≥ 0 | last source instant of the episode |
| `first_command_s` | finite number ≥ 0 or `null` | the **observed** first command; `null` when none was issued |
| `physics_end_s` | finite number ≥ 0 | the last physics instant the run observed |
| `label_cutoff_s` | finite number ≥ 0 or `null` | the last labelled observation's instant; `null` when no row was labelled |
| `outcome` | `complete`, `no_command`, `no_label`, `interrupted_diagnostic` | explicit statement of what the window describes |

Ordering rules, per outcome:
`complete` requires `collection_start_s <= first_command_s <= physics_end_s <= collection_end_s`, a
non-null `label_cutoff_s` with `collection_start_s <= label_cutoff_s`, its `t + 0.1` target covered by
`[collection_start_s, physics_end_s]`, and every required stream present in `source_schedule` with
covered counts/ranges and no gaps outside `permitted_gaps_s`.
`no_command` requires `first_command_s is null` and `label_cutoff_s is null`.
`no_label` requires a non-null `first_command_s` and `label_cutoff_s is null`.
`interrupted_diagnostic` requires the frozen scope mode to be `preselected_target_diagnostic` and records
whatever instants were observed without asserting the `complete` ordering.

Boundaries that change together when ratified: `act/episode_audit.py` (closed window schema, per-outcome
validation at `seal()`, readback parity), `act/continuous_capture.py` (the fields it can supply:
collection start/end from the grid, first command from the event, physics end from finalization, cutoff
from `label_cutoff_s`), `act/recorder.py` (the seal carries the same window, and the v2 readback
re-validates it), and the Task 5 composition that assembles the window.

Current state: `seal()` accepts any non-empty window dictionary, because no key names are frozen.

## Ratification checklist

1. Approve, amend or reject **Proposal A** (raw frames).
2. Approve, amend or reject **Proposal B** (window).
3. For each approval, confirm that a formal run must refuse to seal while the named producer does not yet
   supply the fields — the current fail-closed behaviour stays until the producer wiring lands.

Any amendment is applied by editing this file and the ledger entry that references it, so the ratified
text and the code that implements it stay traceable to one another.
