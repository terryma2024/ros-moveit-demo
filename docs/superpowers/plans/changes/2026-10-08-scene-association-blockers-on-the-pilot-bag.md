# Scene-association blockers found on the pilot bag (SUPERSEDED)

Date: 2026-10-08

Status: SUPERSEDED. The findings below were the state on 2026-10-08 before any decision; the decisions were taken later: item 1 (the stale first scene clock) and the colour by CP-3441 (`2026-10-08-teacher-event-clocks-colour-and-single-final-stop`), the colour root cause by CP-3445 (`2026-10-08-act-move-group-does-not-publish-the-monitored-scene`), the read-bracket and delivery rules by CP-3440 B (`2026-10-08-planning-scene-freshness-by-bracketing`) and the apply-bounded bracket by CP-3449 (`2026-10-08-apply-bounded-scene-bracket`). The text is kept unchanged as the evidence that led to them. (The original status line read: findings with evidence and options, no Teacher code changed, nothing taken yet.)

Trigger: the first-row `LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID` of the pilot bag `031b82c6` with the window rule applied (CP-3440 C), and the next stop behind it.

## 1. The Teacher's first scene call is stamped with a stale simulation clock (178 ms)

- Chain: the SETUP apply (`world_sync` alignment, event seq 1) stamps `request_ros_clock.sim_time_ns = 21.906 s`; the physics was at 22.085 s at that monotonic instant (world and `/clock` records of the same bag), so the Teacher's node clock lagged the simulation by 178 ms while the Teacher was busy with SETUP. The other 16 scene operations lag by 0 to 22 ms; response clocks lag by 0 to 4 ms.
- `select_source` (the timing join "source at most 100 ms before the call in simulation AND monotonic time") then finds no source: the records with sim time in `[21.806, 21.906]` were received 185 to 282 ms before the request (the simulation ran at about real time), so every candidate fails the monotonic half. `RECORDER_SOURCE_ALIGNMENT_UNAVAILABLE worlds=443 too_old=1`, the `world_sync` association is never built, the rows after SETUP keep the `initial` association whose geometry no longer matches the scene: `LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID`. So the first-row error is a consequence, not a defect of the row logic.
- Options: (a) the Teacher stamps scene calls from a current clock (e.g. the newest world record's simulation time when the node clock is stale); (b) the Recorder derives the anchor's simulation time from its own `/clock` + world receipts at the call's monotonic instant (changes the timing join, which QC also uses); (c) the Teacher takes the SETUP apply only after its node clock is current (a wait, no delay of motion).
- Diagnostic used to look past it: `--diagnostic-teacher-clock-repair` (replaces a clock reading more than 30 ms behind the recorded `/clock`; counted, result `DIAGNOSTIC_*`, exit 5). One repair on this bag.

## 2. The ACM-only apply removes the attached cup's colour from every later read

- Evidence (`/so101/raw/planning_scene_reads` and the Teacher events): after `attach` (seq 24, 61.538 s) and its read-back (61.550 s) the scene has `object_colors = {pedestal, plastic_cup, table}`; the Teacher's `acm_apply` (seq 27, 61.572 s) is a scene diff with `robot_state.is_diff = False`, no colours, no world objects; from the next read (61.682 s) on, the colours are `{pedestal, table}` until the `detach` read-back (104.956 s). The same `acm_apply` in the earlier DESCEND phase (49.854 s, cup a world object) removes nothing.
- The association compares the full normalized geometry including colours (`OBJECT_COLORS` is a required component), so every row from 61.682 s to the release fails the geometry check: the whole transport phase. No Teacher read follows the ACM apply, so no association describes the post-ACM scene.
- Options: (a) Teacher: send the ACM diff with `scene.robot_state.is_diff = True` (or re-send the colours), so MoveIt keeps the attached object's colour (needs a live check, one line in the Teacher's `acm_apply` request); (b) Recorder: treat an ACM-only apply as a scene change that owes an association built from the first full read after it (new association kind, QC schema); (c) compare geometry without colours (weakens the check; colours do not affect collision planning). Recommendation: (a); (b) if the Teacher must stay untouched.
- Diagnostic used to look past it: `--diagnostic-ignore-scene-colors` (compares geometry without colours; fresh-process QC still compares them).

## 3. The Teacher's stop clock is one physics step behind the instant it claims

- Evidence (final `normal_stop`, seq 58): `source_clock = {begin = end = 889060.959727 s, sim_time = 115.292 s}`, built from the world record received at 889060.957941 (step 56055, 115.292 s) with `begin_monotonic_ns = max(receipt, confirmed)`. At that later instant the simulation was at step 56056 (115.294 s): the latest raw sample that ended before the stop's begin has sim 115.294 s, 2 ms AFTER the stop's claimed sim time. QC (`episode_qc.verify_native_collection_events`: "last native sample before the stop is 0 to 100 ms older than the stop in simulation time") raises `NATIVE_QC_STOP_NATIVE_STALE`.
- Options: (a) the Teacher takes the stop clock's `begin_monotonic_ns` from the world record's receipt (or its sim time from the record current at `confirmed`); (b) QC compares the stop with the samples that ended before the world record's own receipt (`epoch.received_wall_s`), not before the clock's begin.
- Diagnostic used to look past it: the clock repair also sets a `normal_stop` proof's `source_clock.sim_time_ns` to the recorded `/clock` at its begin instant when it lags by up to 20 ms (counted).

Ledger CP: CP-3440.
