"""One independent ``FULL_RESTART`` per anchor, with teardown proofs.

The plan fixes exactly three restart phases - ``restart_default``, ``restart_left``,
``restart_forward`` - and says what each one has to prove: *"Each phase tears down and
reconstructs the one stack, then passes graph, detector, search, lock, timing and stop gates. The manifest
must contain exactly ``default``, ``left`` and ``forward``, once each."* Design section 10.2 repeats it:
"after the forty scenarios, ``default``, ``left`` and ``forward`` each run one independent
``FULL_RESTART``; all three pass the graph, detection, search, lock, timing and stop gates, and no
consecutive-success counter is kept."

What this producer implements, stated exactly:

* **One stack at a time.** The owner of record is this process. Before an anchor's stack starts, the
  process table, the ROS graph and the GPU compute processes are read and must be empty of owners; the
  stack is then the production composition of ``runtime/launch_composition.py`` for the ACT profile
  (``ros2_control_node`` with the production MuJoCo camera plugin, ``robot_state_publisher`` and the four
  controller spawners), started headless under EGL exactly as the frozen HS-308 transport measurement
  starts it. The camera at 10 Hz, the simulation clock, the joint states and TF are the real production
  transport, not a stand-in.
* **The health gates are measured, not asserted.** The graph gate reads ``ros2 node list`` and refuses on
  a missing owner node or a foreign one. The timing gate reads the real ``/head_camera/color`` stream and
  requires the declared 10 Hz with no duplicate, backward or undeclared-gap stamp. The clock gate requires
  ``/clock`` (the simulator's own time base) to advance. The detector gate requires exactly one detector in
  this process, on CUDA, with CPU fallback disabled and the promoted weights digest.
* **The search is the production closed loop.** One declared anchor of the seal's own ``in_frame_matrix``
  fixes ``search_start_rad``; the seal's ``workspace_matrix`` fixes the cup's world point for that anchor,
  which is written into the stack's one MuJoCo instance through the simulator's own
  ``~/set_free_joint_state`` service. The loop is ``HeadSearchController`` driven by
  ``RosSearchAdapter`` over the real topic stream, and the neck is commanded through the neck controller's
  own ``FollowJointTrajectory`` action. That controller (``so101_mujoco_support/HeadNeckTrajectoryController``)
  accepts a goal only while the single owner's dead-man socket is connected, so the owner of the stack
  activates the neck through ``HeadNeckOwner`` and the restart commands it through the owner's local
  admission. The restart owner *is* the single owner of the stack (the plan's "the qualifier owns every start
  and teardown").
* **The stop proof is the production criterion.** After the terminal, the neck is held and raw
  ``/joint_states`` feedback is sampled; three consecutive samples within the promoted
  ``stop_velocity_rad_s`` are the proof.
* **The teardown is proven.** The stack is stopped, and the process table, the ROS graph and the GPU
  compute processes are read again; all three must be empty before the next anchor may start. A teardown
  that cannot be proven refuses the run and stops it: no second stack is ever started.

The receipt is ``head_search_full_restart_receipt`` - the document
``so101_demo.act.head_search_aggregate`` declares for this phase and re-derives field by field from the
evidence, not the producer's claim.
"""
