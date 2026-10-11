"""The production smoke - the flight, its sealed journal, and the aggregator that reads it.

The plan's Step 3 is one sentence of requirements and one sentence of refusals:

    *"Read back production smoke and 40-scene evidence. The smoke must prove producer -> sealed journal ->
    actual aggregator, correct ``TARGET_LOCKED``, 10 Hz continuity, bounded commands, three-sample stop
    proof and exact runtime identity. A mock/fixture-only result does not pass."*

The installed ``so101_head_search_smoke`` proved something else: planning coverage of the bounded stop plan
against the geometry seal, with no stack, no detector, no journal and its ``--scenario`` flag accepted but
never read (HS-179, HS-315 row 5). That proof is still produced - the plan's coverage gate cites it - but it
is **not** what this phase's success stands on. This module is the smoke the plan asks for:

* **The producer owns the stack.** It takes the exclusive-ownership receipt, refuses unless
  that receipt guards exactly this run root, and then starts the one production composition through
  ``head_search_restarts.run_anchor_restart`` - the same start/stop discipline, the same graph probe, the
  same teardown proof, one anchor of the seal's ``in_frame_matrix``, and the cup placed at the seal's own
  point through the simulator's ``set_free_joint_state`` service. Nothing here re-implements the transport.
* **The flight is the production path.** ``RosSearchAdapter`` + the production ``HeadSearchController``
  over the real ``/head_camera/color``, ``/head_camera/camera_info``, ``/joint_states`` and TF, with the
  neck commanded through the admission-wrapped neck controller. The in-process MuJoCo harness the forty
  scenarios use is a different, ROS-free path; this phase does not use it.
* **The producer writes a sealed journal; the aggregator reads it back.** The raw record - frames, the
  commanded targets, the held stop samples, the graph, the teardown - is written to
  ``sealed-journal.json`` with its own body digest, and :func:`aggregate_production_smoke` then reads that
  **file** and re-derives every gate from it. The document the qualification aggregate's gate consumes,
  ``production-smoke-journal.json``, is the aggregator's output, not the flight's narration.
* **The terminal is classified by the scenario module's own rule.** ``classify_terminal`` builds the entry
  the forty-scenario producer builds and hands it to ``head_search_scenarios.classify_scenario``; the
  smoke's declared class is ``nominal``, so a lock is the only passing terminal and a lock on any other
  class is the wrong-lock failure the plan names. The cadence check and the stop proof are that module's
  too (``check_frame_cadence`` / ``stop_proof``), never a second implementation.

The refusal vocabulary is ``SMOKE_*``. A stack that will not start, a cup that is not locked, a cadence
outside the declared contract, an unbounded command, an unproven stop, a teardown that cannot be proven or
a GPU that was not released each refuse **by name**, and a refused run leaves its sealed journal and its
journal on disk so the reason is readable rather than inferred. A flight that itself refused
(``RESTART_*``) is mapped onto the smoke's own code and the original code is kept verbatim in the detail.
"""
