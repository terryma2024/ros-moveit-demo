"""The phases' stop, feedback, submission and stop-proof measurements: declared or measured, never invented.

Phase 7 consumes five measurement documents this module produces. Two of them are **declarations** the
running controller already carries and this module only reads:

* ``controller_stop_config`` cites the Head neck's own stopped-velocity tolerance - the constant the stop
  window applies to every ``controller_state`` sample, read out of the *installed* ``head_neck_limits``
  module (the one Python home of the stop-window constants) and cross-checked against the same declaration
  in the source tree and against the sealed controller period. Nothing here measures it; the document says ``measured_here: false`` and carries the declaring
  path, digest and source line. A system whose limits module declares no such constant is refused
  (``CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED``); a source tree and an installed limits module that disagree, or a
  window whose step is not the controller's own period, are refused as contradictory.
* ``feedback_measurements`` carries the declared feedback period - the rate `/joint_states` arrives at, which
  is the feedback the stop path's own criterion consumes - and the feedback path's quantisation resolution.
  The period is a declaration read from the sealed controller configuration (both declared rates are
  recorded, and the one the stop path uses is the broadcaster's). The quantisation is **not** declared
  anywhere in this repository: the producer accepts an explicit ``quantisation`` declaration, derives the
  resolution from a declared encoder count and joint travel, and otherwise writes ``null`` with the refusal
  ``CAL_FEEDBACK_QUANTISATION_UNDECLARED`` rather than inventing, defaulting or substituting a number that
  measures something else.

The other three are **measurements** taken in the sealed MuJoCo scene, in simulation time, with no ROS node,
no detector, no CUDA and no hardware:

* ``stationary_measurements`` holds each declared settled pose and samples the monitored joints' velocities
  at the declared feedback period, which is the stationary velocity noise phase 7 turns into
  ``stop_velocity_rad_s``. A pose the declared settle rule never reaches refuses the measurement.
* ``controller_submissions`` submits the targets the *installed* production controller selected (its own
  bounded plan's stops and the anchor's declared search start) through an admission port that writes the
  command interface once per sealed control cycle, exactly as the controller's ``update()`` does, and records
  the simulation instant of the submission snapshot and of the first physics step that consumed the admitted
  target. Every lead is proved to be the simulation clock's: on the sealed timestep grid, inside one control
  period plus one timestep, and equal to the instant the plant itself reported. Nothing is wall-clock, so
  ``CAL_SUBMIT_LEAD_UNVERIFIED`` cannot fire on these records.
* ``stop_proofs`` revokes the neck at declared offsets of a real motion and then decides every feedback
  sample with the **installed** stop criterion - ``RosControllerPort.stopped()``, fed the same
  ``sensor_msgs/JointState`` messages rclpy would deliver - counting the receipts until three *consecutive*
  samples qualify. The interval from the request to the third confirming receipt is the latency phase 7
  bounds, every sample of every window is recorded so one slow sample can be checked, and a window without
  three consecutive qualifying receipts is refused rather than trimmed.

The plant is paced to the monotonic clock (``realtime``, the production loop's own behaviour), so the
monotonic stop latency is a real-time quantity and not an artefact of a fast in-process loop; the achieved
real-time factor and the largest pacing lag are recorded beside it. What this flight cannot measure is a DDS
transport: the submission port is in process, the goal is not encoded into a ROS action message, and the
documents say so (``transport_measured: false``) instead of implying a flight over the wire.

Nothing here starts a ROS node, addresses hardware or renders a frame; the MuJoCo plant is the only heavy
import and it is made inside the call.
"""
