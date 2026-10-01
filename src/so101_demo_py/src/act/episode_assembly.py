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

__all__ = ["assemble_episode_capture"]


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
    )
