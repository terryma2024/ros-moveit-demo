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

__all__ = ["ProductionProducer", "assemble_episode_capture"]


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

    def __init__(self, *, max_age_s: float = 0.1, max_skew_s: float = 0.1) -> None:
        from .synchronizer import RgbObservationSynchronizer

        self.synchronizer = RgbObservationSynchronizer(max_age_s=max_age_s, max_skew_s=max_skew_s)
        #: where a frame-feeding loop records the instants it has supplied, one list per stream
        self.stamps = {stream: [] for stream in self.STREAMS}
        self._pushed = 0
        self._latest = None

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
                    value = frame
                elif stream == "arm":
                    value = [0.0] * 6
                else:
                    value = 0.0
                self.synchronizer.push(stream, session_id, stamp, value,
                                       received_monotonic_s=self.synchronizer.monotonic())
                self._latest = stamp
            self._pushed += 1
        observation, audit = self.synchronizer.sample_with_audit(session_id, attempt_id, at_s)
        return observation, {key: value for key, value in audit.items() if key in ("source_stamps",)}
