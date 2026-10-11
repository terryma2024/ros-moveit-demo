"""Stable macOS task runtime closure, per-run binding and read-back attestation.

Design section 4.1 splits the old single manifest into three layers so that fresh per-run
facts can never be confused with the identity that must survive restarts:

* :class:`RuntimeClosureIdentity` -- only bytes and semantics that are equal across
  restarts: source/submodule commits, the copied install prefix inventory, typed
  executable/library/config inventories and the normalized environment constraints.
  Placement facts (ROS domain, Gazebo partition, session id, evidence root, timestamps)
  are deliberately absent and cannot leak in.
* :class:`RunBinding` -- the per-run facts (campaign/batch, fresh ROS domain, station
  session, evidence root, owner generation, start time).
* :class:`RuntimeAttestation` -- what was really observed after the spawn: process
  identities, loaded image paths read back from the process and the observed ROS domain.

Everything is fail closed: a drifted inventory, a missing submodule commit, a symlinked or
replaced file, a contaminated install prefix, a loaded image that comes from outside the
copied install, or a ROS domain that does not match the run binding raises
:class:`RuntimeClosureError` with a stable ``code``.
"""
