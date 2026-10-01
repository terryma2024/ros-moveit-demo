"""Assemble one episode's capture from the parts a physical run already holds.

The first-episode path owns the episode's directory and identity; the physical side owns the producer. This module is
the seam between them, so that neither has to know the other's internals: a caller that has a sampler (an object with
`sample_with_audit(session_id, attempt_id, at_s)`), a `physical_audit` callable and optionally a step guard, plus the
episode's root, scope and identity, gets back a `ContinuousEpisodeCapture` wired to a real recorder and audit writer.

Everything here is proven by the chain test in `test_act_seal_and_downgrade.py`: the recorder creates the episode
directory and refuses to reuse one, the audit writer roots at that same directory (its manifest lands in `<root>/audit/`,
where verification resolves it), and the scope document is the audit's own `source.json` - three facts that took a
stretch of refusals to establish, and which this function keeps in one place instead of leaving to each caller.
"""

from __future__ import annotations

from pathlib import Path

from .continuous_capture import ContinuousEpisodeCapture
from .episode_audit import EpisodeAuditWriter
from .recorder import EpisodeRecorder

__all__ = ["EpisodeSink", "LiveSampler", "PhysicalAuditAdapter", "PointEpisode",
           "ProductionProducer", "assemble_episode_capture", "episode_audit_pair"]


def assemble_episode_capture(
    *,
    sampler,
    physical_audit,
    identity: dict,
    provenance: dict,
    inputs: dict,
    episode_root: Path,
    scope: dict,
    guard=None,
    audit_writer=None,
    scope_path=None,
    **capture_options,
) -> ContinuousEpisodeCapture:
    """Build the capture for one episode, with its recorder and audit writer.

    `episode_root` is created by the recorder and owned by it; the audit writer roots at the same directory - it accepts
    an existing one for exactly that reason - so its manifest sits at `<episode_root>/audit/audit-manifest.json`, which
    is where `verify_episode_seal` and the endpoint QC resolve it.

    `scope` is the audit's scope **document**, not a path: the writer takes the document, while `Recorder.finish` takes
    the path of the file the writer puts it in (`<root>/audit/source.json`). Passing a `Path` here raises
    `AUDIT_ROOT_INVALID` - the writer validating its arguments - which is how this signature was corrected.
    """
    episode_root = Path(episode_root)
    recorder = EpisodeRecorder(
        episode_root,
        session_id=identity["session_id"],
        attempt_id=identity["attempt_id"],
        reset_epoch=identity["reset_epoch"],
        provenance=provenance,
    )
    audit = EpisodeAuditWriter(episode_root, scope, identity, inputs)
    return ContinuousEpisodeCapture(
        recorder=recorder,
        sampler=sampler,
        physical_audit=physical_audit,
        guard=guard,
        audit=audit,
        audit_writer=audit_writer,
        **({} if scope_path is None else {"scope": scope_path}),
        # the capture's own remaining options - `scope` (the path of the file the writer puts the scope document in,
        # which is not the document itself), `deadline_s`, `monotonic` - pass straight through rather than being
        # duplicated here, so a caller that needs them is not forced to assemble the recorder and writer by hand
        **capture_options,
    )


class ProductionProducer:
    """The production producer behind the sampler interface the capture calls.

    It owns a real `RgbObservationSynchronizer` - the class the live path uses to pair camera streams with simulation
    time - and presents it to `ContinuousEpisodeCapture` as its `sampler`. The capture calls
    `sample_with_audit(session_id, attempt_id, at_s)` and expects an `(observation, source_audit)` pair; this class
    supplies the frames that instant needs and narrows the audit to what an episode row records.

    Three properties are worth knowing, each learned by driving the real synchronizer rather than by reading it:

    * every stream it buffers must hold a stamp within `max_age_s` of the instant and their stamps must agree within
      `max_skew_s`, because `causal_sample` runs over all of them and refuses with `INPUT_STALE` otherwise - so a stream
      with nothing recorded for that instant carries the instant itself;
    * the receipt time must come from the synchronizer's own clock, which is what its sampling compares against, or the
      frame is stale the instant it is pushed;
    * and its audit carries `source_received_wall_s` and `neck_yaw_rad` beyond the closed sixteen keys the recorder
      accepts, so what the capture is handed is narrowed to `source_stamps` - the same seam as `_RECORDER_LOCAL_KEYS`,
      seen from the source side.
    """

    STREAMS = ("head", "wrist", "arm", "neck")

    def __init__(self, *, max_age_s: float = 0.1, max_skew_s: float = 0.1, frames=None) -> None:
        from .synchronizer import RgbObservationSynchronizer
        #: where a frame comes from for a stream at an index - the run's own camera frames when it has
        #: them. The default synthesises zeroes, which is enough for a harness and wrong for a live run:
        #: the capture compares each row's pixels against the acquisition it recorded
        #: (`ACQUISITION_PIXEL_MISMATCH`), so a real episode must push the frames it actually captured.
        self.frames = frames

        self.synchronizer = RgbObservationSynchronizer(max_age_s=max_age_s, max_skew_s=max_skew_s)
        #: where a frame-feeding loop records the instants it has supplied, one list per stream
        self.stamps = {stream: [] for stream in self.STREAMS}
        self._pushed = 0
        self._latest = None
        #: the synchronizer's own audit from the last sample (CP-2842)
        self.last_source_audit: dict = {}

    def sample_with_audit(self, session_id, attempt_id, at_s):
        """Return the observation for `at_s` and the source audit an episode row records."""
        import numpy as np

        if self._pushed == 0:
            self.synchronizer.reset(session_id)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        while self._pushed < max(len(self.stamps[stream]) for stream in self.STREAMS):
            for stream in self.STREAMS:
                recorded = self.stamps[stream]
                stamp = float(recorded[self._pushed]) if self._pushed < len(recorded) else self._latest
                if stamp is None:
                    continue
                if stream in ("head", "wrist"):
                    value = frame if self.frames is None else self.frames(stream, self._pushed)
                elif stream == "arm":
                    value = [0.0] * 6
                else:
                    value = 0.0
                self.synchronizer.push(stream, session_id, stamp, value,
                                       received_monotonic_s=self.synchronizer.monotonic())
                self._latest = stamp
            self._pushed += 1
        observation, audit = self.synchronizer.sample_with_audit(session_id, attempt_id, at_s)
        # the full audit is kept here for the extraction path, which needs the receipt mapping as well
        # (`live_evidence_sample`'s `source_received_monotonic_s`); the episode row still records only `source_stamps`,
        # because the recorder's channel is closed at sixteen keys (CP-2842)
        self.last_source_audit = dict(audit)
        return observation, {key: value for key, value in audit.items() if key in ("source_stamps",)}

    def source_received_monotonic_s(self) -> dict:
        """The receipt times of the last sample, by stream - for the extraction, not for a row.

        `live_evidence_sample` takes this mapping while the recorder refuses it, so the two travel separately: this
        accessor is the extraction's, and `sample_with_audit`'s audit is the row's.
        """
        return dict(self.last_source_audit.get("source_received_wall_s") or {})


def episode_audit_pair(episode_root: Path) -> tuple[Path, Path]:
    """The manifest and scope a sealed episode's audit lives at, given the episode's own directory.

    The audit writer roots at the episode directory and puts its document at `<root>/audit/`, which is where the
    recorder, `verify_episode_seal` and the endpoint QC all resolve it by convention - measured, not assumed (CP-2768).
    Callers that seal an episode and then hand it to a store or a verifier need exactly this pair, and nothing about it
    is obvious from either side, so it lives here beside the seam rather than in each of them.

    Note the phase: a store renames `working/` to `sealed/` when it publishes, so a caller verifying *before* the
    publish uses the working path and one verifying *after* uses the published one (CP-2777) - this function names the
    pair inside whichever root it is given, and the caller supplies the right one.
    """
    audit_dir = Path(episode_root) / "audit"
    return audit_dir / "audit-manifest.json", audit_dir / "source.json"


class PhysicalAuditAdapter:
    """Present the run's physical evidence as the capture's `physical_audit` callable.

    The capture builds each row's audit from three pieces and then requires the recorder's closed sixteen keys
    (`continuous_capture.py:419-422`): what this callable returns, the sampler's `source_stamps`, and the two
    acquisition ids the capture adds. So this callable owes exactly the remaining thirteen -

        reset_epoch  release_epoch  release_event  release_time_s  physical_stamps  phase
        reference_time_s  reference_source  reference_positions
        mujoco_truth  contacts  planning_scene  controller_state

    - and that is the whole of its job: take the values the extraction produces for an instant, insist that all thirteen
    are present, and hand them over. A missing one fails at the sample as `CAPTURE_PHYSICAL_AUDIT_INVALID`, which is
    where a wiring mistake should surface, not at the seal after an episode has been recorded.

    The extraction itself - reading those values out of the capture path - is the coordinator's side of the divided work;
    this class exists so that whatever it produces is checked against the contract in one place.
    """

    KEYS = ("reset_epoch", "release_epoch", "release_event", "release_time_s", "physical_stamps", "phase",
            "reference_time_s", "reference_source", "reference_positions",
            "mujoco_truth", "contacts", "planning_scene", "controller_state")

    def __init__(self, evidence) -> None:
        #: a callable taking `at_s` and returning the thirteen physical values for that instant
        self.evidence = evidence

    def __call__(self, at_s: float) -> dict:
        values = self.evidence(at_s)
        missing = [key for key in self.KEYS if key not in values]
        if missing:
            raise ValueError(f"PHYSICAL_AUDIT_INCOMPLETE: {sorted(missing)}")
        return {key: values[key] for key in self.KEYS}


class LiveSampler:
    """Present an already-fed `RgbObservationSynchronizer` to the capture as its `sampler`.

    The difference from `ProductionProducer` is who feeds the synchronizer. A live run does that itself - the ROS
    observation adapter pushes each camera frame as it arrives - so nothing here should invent or replay anything: this
    class only delegates `sample_with_audit` and keeps the synchronizer's own audit available to the extraction, exactly
    as `ProductionProducer` does (`last_source_audit`, `source_received_monotonic_s()`), while leaving the recorded row's
    audit narrowed to `source_stamps`.

    `ProductionProducer` remains the harness's feeder: it pushes what a test has recorded, because a test has no camera.
    Using it against a live synchronizer would push synthetic frames alongside the real ones and, sooner or later, the
    capture's pixel check (`ACQUISITION_PIXEL_MISMATCH`) would say so.
    """

    def __init__(self, synchronizer) -> None:
        self.synchronizer = synchronizer
        self.last_source_audit: dict = {}

    def sample_with_audit(self, session_id, attempt_id, at_s):
        observation, audit = self.synchronizer.sample_with_audit(session_id, attempt_id, at_s)
        self.last_source_audit = dict(audit)
        return observation, {key: value for key, value in audit.items() if key in ("source_stamps",)}

    def source_received_monotonic_s(self) -> dict:
        """The receipt times of the last sample, by stream - for the extraction, not for a row (CP-2842)."""
        return dict(self.last_source_audit.get("source_received_wall_s") or {})


class PointEpisode:
    """The per-point object a run's capture port and its worker runtime both hold.

    A run captures RGB in one object (the `capture_rgb` port) while the episode's coordinates and lifecycle live in
    another (the worker runtime), so the two need something shared to record through. This is it: it owns the
    synchronizer the frames are pushed into, the capture assembled around that synchronizer, and the identity the row
    audit and the seal need - and offers the three things the two sides ask of it.

    `push` is what the capture port calls with the pixels and the simulation stamp it already has - the stamp the
    capture receipt calls `source_stamp_monotonic_s`, which the runtime requires to be `ros_sim` and which is therefore
    simulation time rather than wall time. `start` and `finish` are what the worker runtime calls at the episode's
    boundaries; `finish` needs the window, or the capture does not seal at all.
    """

    def __init__(self, *, identity: dict, provenance: dict, inputs: dict, episode_root, scope,
                 scope_path: str, physical_audit, guard=None, deadline_s: float = 120.0,
                 monotonic=None, max_age_s: float = 0.1, max_skew_s: float = 0.1) -> None:
        from .synchronizer import RgbObservationSynchronizer

        self.identity = dict(identity)
        self.synchronizer = RgbObservationSynchronizer(max_age_s=max_age_s, max_skew_s=max_skew_s)
        self.capture = assemble_episode_capture(
            sampler=LiveSampler(self.synchronizer), physical_audit=physical_audit, identity=self.identity,
            provenance=provenance, inputs=inputs, episode_root=episode_root, scope=scope,
            scope_path=scope_path, guard=guard, deadline_s=deadline_s,
            **({} if monotonic is None else {"monotonic": monotonic}))
        # the synchronizer refuses a push whose session does not match the one it was reset for, so the reset is part
        # of beginning an episode rather than something the caller has to remember
        self.synchronizer.reset(self.identity["session_id"])
        self._minter = None
        self._started = False
        self._start_s = 0.0
        self._latest_s = None

    def push(self, camera: str, *, stamp_s: float, pixels, received_monotonic_s: float | None = None) -> None:
        """Record one captured frame: mint its acquisition, hand it to the capture, and push it for sampling.

        The three steps happen here rather than at either caller because this is where the pixels, the stamp and the
        capture are all in reach - re-reading a written PNG would need a decoder and would put the frame behind its own
        acquisition.
        """
        from .acquisition import AcquisitionMinter

        if self._minter is None:
            self._minter = AcquisitionMinter()
        frame = self._minter.mint(
            camera, session_id=self.identity["session_id"], reset_epoch=self.identity["reset_epoch"],
            stamp_s=float(stamp_s), received_monotonic_ns=int(float(stamp_s) * 1e9) + 1, pixels=pixels)
        self.capture.on_acquisition(frame, pixels)
        self.synchronizer.push(camera, self.identity["session_id"], frame.stamp_s, pixels,
                               received_monotonic_s=received_monotonic_s)
        self._latest_s = frame.stamp_s

    def push_numeric(self, *, stamp_s: float, arm=None, neck=None) -> None:
        """Push the numeric evidence an instant needs.

        `causal_sample` runs over **every** stream buffer and refuses with `INPUT_STALE` when one of them holds no
        stamp within `max_age_s` (CP-2824), so the two non-camera streams the sampler reads - `arm` for the joint state
        and `neck` for the yaw - have to be fed alongside the frames even though no acquisition is minted for them.
        """
        session_id = self.identity["session_id"]
        if arm is not None:
            self.synchronizer.push("arm", session_id, float(stamp_s), list(arm),
                                   received_monotonic_s=self.synchronizer.monotonic())
        if neck is not None:
            self.synchronizer.push("neck", session_id, float(stamp_s), float(neck),
                                   received_monotonic_s=self.synchronizer.monotonic())

    def start(self, start_s: float) -> None:
        """Begin the episode at the run's own start instant."""
        self.capture.start(self.identity["session_id"], self.identity["attempt_id"],
                           self.identity["reset_epoch"], float(start_s))
        self._start_s = float(start_s)
        self._started = True

    def finish(self, end_s: float, *, outcome: dict):
        """Seal the episode: the window is `[the gate's instant, this boundary]`, and without it there is no seal."""
        return self.capture.finish(float(end_s), window={"start_s": self._start_s, "end_s": float(end_s),
                                                         "label_cutoff_s": float(end_s)}, outcome=outcome)


class EpisodeSink:
    """The one object a capture port and a worker runtime can both be given before either exists.

    A run builds its `capture_rgb` port first and hands it to the worker runtime afterwards, so the port cannot be
    given the episode itself - the episode does not exist until a point starts. This is the small shared thing in
    between: the runtime sets `current` when it opens a point's episode and clears it when the point ends, and the port
    asks for it while it has the pixels in hand. Everything else about recording lives in `PointEpisode`.
    """

    def __init__(self) -> None:
        self.current = None
        #: the outcome the episode will be sealed with, set by whoever knows it - the run's own decision. It is not
        #: derived here: an episode's status is a fact about the run, and inventing one is exactly what this task
        #: forbids (a fabricated PASS makes every later PASS meaningless).
        self.outcome: dict | None = None

    def record(self, camera: str, *, stamp_s: float, pixels, received_monotonic_s: float | None = None) -> bool:
        """Offer one captured frame to the current episode; returns whether anything took it.

        A run without an open episode - a calibration pass, a dry run, a port used outside an episode - is not an error,
        and returning a boolean rather than raising keeps that distinction where it belongs.
        """
        episode = self.current
        if episode is None:
            return False
        episode.push(camera, stamp_s=stamp_s, pixels=pixels, received_monotonic_s=received_monotonic_s)
        return True

    def finish(self, end_s: float):
        """Seal the current episode at the run's own end boundary; no episode means nothing to seal.

        The outcome has to have been set first - `Recorder.finish` refuses a document whose status and reason do not
        agree with themselves, and this class has no business guessing either.
        """
        episode = self.current
        if episode is None:
            return None
        if self.outcome is None:
            raise ValueError("EPISODE_OUTCOME_MISSING")
        return episode.finish(end_s, outcome=dict(self.outcome))
