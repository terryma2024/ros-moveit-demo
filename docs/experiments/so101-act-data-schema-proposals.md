# Schema proposals awaiting owner ratification (Task 3)

**RATIFIED 2026-09-30 by the owner.** All three proposals below are approved as written: A (raw controller
reference frames) is approved for implementation, B (collection window) is approved for implementation,
and C is approved for adopting the registered `act/contact_live.py` live sample per kind **together with
explicit authorisation to replace the literal `planning_scene_ok: True` assertions**
(`adapters/act/pick_place_search_port.py:412`, `adapters/act/pick_place_search_boundary.py:282`) with real
observations, defining the Planning Scene and gripper/controller feedback records as proposed. The owner
also chose to converge Task 3 first: push these schemas through the producer boundaries and then send the
fifth checkpoint. Any later amendment is recorded here and in the ledger.

The text below was written before ratification and is kept unchanged so the ratified contract and the
proposals that were reviewed stay comparable. The Task 3 reviewer ruled that the exact
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


## Proposal C — physics source records (`physics.jsonl`)

Derived from the **registered** contract rather than invented: `act/contact_live.py` already defines the
live contact sample and its per-contact record, and both are closed there.

Registered sample keys (`act/contact_live.py:25-32`): `simulation_session_id`, `reset_epoch`,
`physics_step`, `simulation_time_s`, `model_qpos`, `model_qvel`, `cup_position_m`, `cup_velocity_m_s`,
`left_contacts`, `right_contacts`, `other_contacts`, `truncated`, `diagnostic_hazard_breached`.
Registered contact keys (`act/contact_live.py:33-35`): `robot_geom`, `object_body`, `normal_force_n`,
`signed_distance_m` — one record per contact, in the three lists.

Proposed shape for a physics row's `observation`: the registered sample verbatim, with its own
`simulation_time_s` equal to the row's envelope clock (already enforced) and every contact entry closed to
the four registered keys.

Required members per kind (the measurements the verdict is made of):

| Kind | Required members beyond `simulation_time_s` and `physics_step` |
| --- | --- |
| `contact` | `left_contacts`, `right_contacts`, `other_contacts`, `cup_position_m` |
| `support` | `left_contacts`, `right_contacts`, `cup_position_m`, plus the runner's verified `supported` flag |
| `pose` | `cup_position_m`, `model_qpos` |
| `retract` | `cup_position_m`, `cup_velocity_m_s` |

Ordering and integrity rules: `reset_epoch` and `physics_step` are non-negative integers, the contact
lists contain only closed contact records, `truncated` and `diagnostic_hazard_breached` are booleans, and
`contact` rows require both `truncated` and `diagnostic_hazard_breached` to be present so a truncated
observation cannot be read as a complete one.

**What this replaces, and what it waits on.** Today the physics observation accepts the MuJoCo
`evidence_dict` fields (counts, one maximum force, a geometry-name list) which are **summaries**; the
reviewer's requirement is the full robot contact pairs plus an independent Planning Scene record and
gripper/controller feedback. This proposal supplies the first of those three from the registered contract.
The remaining two still need their source located and ratified: `planning_attached` is exposed per request
by the port/boundary adapters (`adapters/act/pick_place_search_boundary.py:409`, `:526`) rather than as a
recorded observation, and no gripper/controller feedback record has been identified yet. Both belong in
this proposal before the boundary changes together, and the formal-seal gate stays in place until then.

Boundaries that change together when ratified: the port/backend that produces each phase's
`physical_observation` (currently `backends/mujoco/qualified_phases/release_retreat.py`), the runner's
`_raw()` and `_physics()`, `act/episode_audit.py` (closed physics observation schema, required members per
kind, readback parity) and any test fixtures that stand in for a real port.


### Where the last two records stand (recon result, 2026-09-30)

Neither exists as a recorded observation today, and that is a finding about the **producers**, not only
about the schema:

- **Planning Scene**: `planning_scene_ok` is a boolean in the runner's and the port's closed evidence sets
  (`act/pick_place_runner.py:45,59,69,231`, `adapters/act/pick_place_search_port.py:33,41`), and at least
  two sites **construct it as a literal** — `adapters/act/pick_place_search_port.py:412` and
  `adapters/act/pick_place_search_boundary.py:282` set `"planning_scene_ok": True` rather than reading a
  scene. No closed record of attached objects, scene diff or scene revision was found anywhere under
  `act/` or `adapters/act/`.
- **Gripper/controller feedback**: the closest existing state is the broker's controller state
  (`adapters/act/ros_broker.py`) and the per-request fields the port exposes; no feedback record with a
  gripper opening, commanded versus measured positions, or a controller status sequence was found.

Consequences to ratify together with the shapes above: (1) a Planning Scene observation record and a
gripper/controller feedback record must be **defined** (values, units, source revision and stamp), because
nothing registered exists to adopt; (2) the adapters that currently assert `planning_scene_ok: True` must
**observe** instead — otherwise a formal episode would carry a boolean whose truth no source produced; and
(3) the physics proposal must say which kinds require them, so the formal gate can refuse a run whose
scene/feedback evidence is asserted rather than observed.


## Amendment request A.1 — `evaluation` must be per kind (found while wiring the broker)

Reading `adapters/act/ros_broker.py::reference_state` (lines 291-333) to expose the ratified shape shows
that the two controller kinds are evaluated **independently and differently**: inside the same call, one
kind may resolve through a proven accepted interval (using `self._records[gid]['accepted_sim_s']` and
`direct_goal_reference(record, kind, when)`) while the other is taken from the latest publication
(`stamp`), and each appends its own positions and velocities to the fused result. The method's return is
exactly four keys — `positions`, `velocities`, `accelerations`, `requested_sim_time_s` — with no names, no
per-kind breakdown and no acceptance identity.

A single flat `evaluation` block therefore cannot describe that call honestly: it would have to claim one
`basis`, one `goal_id` and one acceptance stamp for a reference whose arm dimension came from an accepted
interval and whose gripper dimension came from a publication.

**Requested amendment:** move `evaluation` inside each frame, i.e.
`frames[kind].evaluation = {requested_sim_time_s, basis, goal_id, accepted_sim_s, revoked_sim_s}`, and keep
`projected_positions`/`projection_map` at the record level. The alternative — restricting each record to a
single controller kind — would split one logical reference into two records and change how the capture and
the label join them, so it is the less faithful option. The audit schema currently implements the ratified
flat form (CP-1984), so this amendment changes the same boundary again; nothing in the broker has been
modified yet, and the fail-closed gates mean no formal audit can be sealed either way in the meantime.

The reviewer's constraint that an outer six-dimensional projected reference needs "an explicit checked
mapping" is unaffected: the map stays at the record level and still has to resolve inside the frames and
equal the projection.
