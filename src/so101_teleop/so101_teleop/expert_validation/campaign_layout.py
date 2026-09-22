"""The macOS campaign journal as a verified projection source.

The macOS campaign compositions write the *same* ``CoordinatorJournal`` (and therefore the same
coordinator epoch, chain and committed watermark) under ``<batch_root>/journal``, and they commit
the same canonical vocabulary: ``CAMPAIGN_STARTED``, ``WORKER_REGISTERED``, ``POINT_LEASED``,
``ATTEMPT_STARTED``, ``RESULT_COMMITTED``, ``POINT_TERMINAL``, ``BATCH_TERMINAL`` and
``CLEANUP_COMMITTED``. What differs is the payload schema, and this module is the one place that
knows about it:

* ``CAMPAIGN_STARTED`` carries ``campaign_id``/``batch_id``/``schema_version`` and no runtime
  identity. The config hash is read from the batch's own ``selection-binding.json``, and that
  document must be the binding the journal references: every ``POINT_LEASED`` carries the same
  ``selection_sha256``. Nothing is invented; a layout that publishes neither refuses.
* ``RESULT_COMMITTED`` carries the business ``outcome`` but not the result hash. The campaign
  commits the point's result hash with its own ``POINT_TERMINAL`` (``state == "COMMITTED"``), so the
  adapter pairs the two events: exactly one terminal per (point, attempt), same outcome, and the
  hash comes from that terminal. A result without its terminal is refused, never guessed.
* ``BATCH_TERMINAL`` carries the campaign's own verdict in ``outcome``.
* Every committed result must also have the campaign's durable per-point document
  (``<batch_root>/point-results/<point_id>.json``) with ``committed is True`` and the same point,
  attempt, outcome and lease identity. That document is the campaign's own evidence record; a
  missing or inconsistent one is refused rather than projected.

Everything else fails closed: an event this adapter does not translate (for example the campaign's
``ATTEMPT_FAILED`` infrastructure record, which has no canonical equivalent here) refuses the whole
projection instead of being silently skipped. No artifact is imported on this layout: the campaign
compositions do not write sealed ``workers/**/sealed`` attempt manifests, and a synthetic reference
to one is exactly what must never be fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

from so101_demo.parallel_batch.contracts import AttemptIdentity

from .committed_artifacts import CommittedAttemptEvidence
from .coordinator_events import (
    AcceptedCoordinatorCursor,
    CampaignUpstreamBinding,
    CoordinatorProjectionError,
    UpstreamEventView,
    _CANONICAL,
    _journal_format,
    _next_cursor,
    _verified_history,
)
from .reducer import CanonicalCampaignReducer, ReducerError, projection_document


#: Where the campaign compositions write the durable per-point committed document.
POINT_RESULTS_DIRNAME = "point-results"

#: Where the campaign adapter writes the binding that its leases and points were selected from.
SELECTION_BINDING_NAME = "selection-binding.json"

#: The canonical-subset vocabulary this adapter translates. Anything else refuses.
_TRANSLATED_EVENT_TYPES = frozenset(
    {
        "CAMPAIGN_STARTED",
        "WORKER_REGISTERED",
        "POINT_LEASED",
        "ATTEMPT_STARTED",
        "RESULT_COMMITTED",
        "POINT_TERMINAL",
        "BATCH_TERMINAL",
        "CLEANUP_COMMITTED",
    }
)

#: The two hashes every binding names for itself, under the same name in both vocabularies.
_HASH_FIELDS = ("selection_sha256", "config_sha256")

#: The binding kind whose selection is named in the retry vocabulary. A ``FIRST_PASS`` binding names
#: the catalog ``catalog_sha256`` and lists its points as ``points`` / ``selected_point_ids``; this
#: kind's binding names the catalog its one point was selected from ``original_catalog_sha256`` and
#: that point ``point``. One binding, one selection: neither vocabulary is inferred from the other,
#: and a document that names neither - or that names both with contradicting values - is refused.
_RETRY_KIND = "FULL_RESTART_RETRY"

#: The campaign's own terminal verdicts, translated into the canonical terminal vocabulary. A
#: campaign PASS label is the campaign's statement that cleanup is proven, every worker was ACTIVE,
#: the lane served its minimum, nothing was refused and every selected point executed exactly once
#: with its durable evidence - exactly the canonical ``POINTS_COMPLETE`` fact, no more and no less.
#: Every other verdict keeps its own name, so a reader can never mistake an incomplete campaign for
#: a complete one.
_CAMPAIGN_PASS_VERDICTS = frozenset({"W2_CAMPAIGN_PASS", "N1_CAMPAIGN_PASS"})
POINTS_COMPLETE = "POINTS_COMPLETE"


@dataclass(frozen=True, slots=True)
class CampaignLayoutBatch:
    """Verified campaign events, the reduced canonical state and the cursor to accept."""

    events: tuple[UpstreamEventView, ...]
    next_cursor: AcceptedCoordinatorCursor
    projected_state: Mapping[str, object]
    campaign_id: str


def _require_id(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CoordinatorProjectionError(f"CAMPAIGN_FIELD_INVALID:{name}")
    return value


def _require_optional_int(name: str, value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CoordinatorProjectionError(f"CAMPAIGN_FIELD_INVALID:{name}")
    return value


def _require_hash(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise CoordinatorProjectionError(f"CAMPAIGN_FIELD_INVALID:{name}")
    return value


def _safe_regular(path: Path, root: Path) -> Path:
    """A path that must exist as a regular file directly inside ``root``."""

    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise CoordinatorProjectionError("CAMPAIGN_POINT_RESULT_INVALID") from error
    if path.is_symlink() or not resolved.is_file():
        raise CoordinatorProjectionError("CAMPAIGN_POINT_RESULT_INVALID")
    return resolved


def _binding_catalog_sha256(binding_document: Mapping[str, object]) -> str:
    """The catalog digest a binding names, in either vocabulary, verified or refused.

    The retry name is only the retry kind's: a binding that does not declare itself a
    ``FULL_RESTART_RETRY`` may not borrow it. When a document names both, both must name one digest
    - two catalogs in one binding is a contradiction, not an alias.
    """

    named = binding_document.get("catalog_sha256")
    original = binding_document.get("original_catalog_sha256")
    if isinstance(named, str) and isinstance(original, str) and named != original:
        raise CoordinatorProjectionError("CAMPAIGN_FIELD_INVALID:catalog_sha256")
    if binding_document.get("kind") == _RETRY_KIND and named is None:
        named = original
    return _require_hash("catalog_sha256", named)


def _binding_point_ids(binding_document: Mapping[str, object]) -> tuple[str, ...]:
    """The selected point ids a binding names, in either vocabulary, or a refusal.

    A retry binding has no ``selected_point_ids`` list: the one point it executes, named ``point``,
    is its selection. The ids are read from the binding only; the document's top-level summary is
    cross-checked against them by the caller and never substituted for them.
    """

    point_ids: object = binding_document.get("selected_point_ids")
    if point_ids is None and binding_document.get("kind") == _RETRY_KIND:
        point = binding_document.get("point")
        point_ids = [point.get("point_id")] if isinstance(point, Mapping) else None
    if (
        not isinstance(point_ids, (list, tuple))
        or not point_ids
        or any(not isinstance(point_id, str) or not point_id for point_id in point_ids)
    ):
        raise CoordinatorProjectionError("CAMPAIGN_BINDING_INVALID")
    return tuple(point_ids)


def read_selection_binding(binding: CampaignUpstreamBinding) -> Mapping[str, object]:
    """The batch's own selection binding, verified against the journal that references it.

    What is verified is the *selection*: the two hashes both vocabularies name identically, the
    catalog the batch was selected from, and the points it was selected to execute. The composed
    campaign writes those same facts in two vocabularies - the first pass's, and the retry's
    ``_RETRY_KIND`` vocabulary described above - and both are read here, so a retry batch's own
    binding is read by the same reader as a first pass's. The binding document is returned as the
    batch wrote it: nothing is renamed, and no field is invented for a document that did not carry
    it.
    """

    path = Path(binding.batch_root) / SELECTION_BINDING_NAME
    try:
        raw = _safe_regular(path, Path(binding.batch_root)).read_text(encoding="utf-8")
        document = json.loads(raw)
        binding_document = document["binding"]
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise CoordinatorProjectionError("CAMPAIGN_BINDING_INVALID") from error
    if not isinstance(binding_document, Mapping):
        raise CoordinatorProjectionError("CAMPAIGN_BINDING_INVALID")
    if (
        binding_document.get("batch_id") != binding.batch_id
        or binding_document.get("campaign_id") != binding.campaign_id
    ):
        raise CoordinatorProjectionError("CAMPAIGN_BINDING_INVALID")
    for name in _HASH_FIELDS:
        _require_hash(name, binding_document.get(name))
    catalog_sha256 = _binding_catalog_sha256(binding_document)
    point_ids = _binding_point_ids(binding_document)
    # The document's own top-level summary is written from this same binding, so it has to name the
    # same selection. It is a cross-check, never a second source: a disagreement is a refusal.
    summary_ids = document.get("selected_point_ids")
    if summary_ids is not None and (
        not isinstance(summary_ids, (list, tuple)) or tuple(summary_ids) != point_ids
    ):
        raise CoordinatorProjectionError("CAMPAIGN_BINDING_INVALID")
    summary_catalog = document.get("catalog_sha256")
    if isinstance(summary_catalog, str) and summary_catalog != catalog_sha256:
        raise CoordinatorProjectionError("CAMPAIGN_FIELD_INVALID:catalog_sha256")
    return binding_document


def _terminal_index(history) -> dict[tuple[str, str], tuple[str, str]]:
    """The campaign's own committed result hash per (point, attempt), from POINT_TERMINAL."""

    terminals: dict[tuple[str, str], tuple[str, str]] = {}
    for event in history:
        if event.type != "POINT_TERMINAL":
            continue
        payload = event.payload
        point_id = payload.get("point_id")
        attempt_id = payload.get("attempt_id")
        if not isinstance(point_id, str) or not point_id:
            raise CoordinatorProjectionError("CAMPAIGN_TERMINAL_INVALID")
        if not isinstance(attempt_id, str) or not attempt_id:
            # A terminal that names no attempt cannot confirm a committed result.
            raise CoordinatorProjectionError("CAMPAIGN_TERMINAL_INVALID")
        if payload.get("state") != "COMMITTED":
            raise CoordinatorProjectionError("CAMPAIGN_TERMINAL_INVALID")
        outcome = payload.get("outcome")
        if not isinstance(outcome, str) or not outcome:
            raise CoordinatorProjectionError("CAMPAIGN_TERMINAL_INVALID")
        result_sha256 = _require_hash("result_sha256", payload.get("result_sha256"))
        key = (point_id, attempt_id)
        if key in terminals:
            raise CoordinatorProjectionError("CAMPAIGN_TERMINAL_DUPLICATE")
        terminals[key] = (outcome, result_sha256)
    return terminals


def _point_result_document(
    binding: CampaignUpstreamBinding,
    payload: Mapping[str, object],
    point_id: str,
    attempt_id: str,
    outcome: str,
) -> Mapping[str, object]:
    """The campaign's own durable committed document for one result, verified."""

    path = Path(binding.batch_root) / POINT_RESULTS_DIRNAME / f"{point_id}.json"
    try:
        document = json.loads(_safe_regular(path, Path(binding.batch_root)).read_text("utf-8"))
    except (OSError, TypeError, ValueError) as error:
        raise CoordinatorProjectionError("CAMPAIGN_POINT_RESULT_INVALID") from error
    if not isinstance(document, Mapping):
        raise CoordinatorProjectionError("CAMPAIGN_POINT_RESULT_INVALID")
    if (
        document.get("committed") is not True
        or document.get("point_id") != point_id
        or document.get("attempt_id") != attempt_id
        or document.get("outcome") != outcome
    ):
        raise CoordinatorProjectionError("CAMPAIGN_POINT_RESULT_INVALID")
    lease_identity = document.get("lease_identity")
    if lease_identity is not None:
        if (
            not isinstance(lease_identity, (list, tuple))
            or len(lease_identity) != 6
            or lease_identity[1] != binding.batch_id
            or lease_identity[2] != point_id
            or lease_identity[3] != attempt_id
        ):
            raise CoordinatorProjectionError("CAMPAIGN_POINT_RESULT_INVALID")
    for name in ("evidence_manifest_sha256", "dynamic_manifest_sha256"):
        durable = document.get(name)
        observed = payload.get(name)
        if isinstance(durable, str) and isinstance(observed, str) and durable != observed:
            raise CoordinatorProjectionError("CAMPAIGN_POINT_RESULT_MISMATCH")
    return document


class CampaignLayoutReader:
    """Verify one campaign journal and reduce it into the canonical campaign state."""

    def __init__(self, journal, binding: CampaignUpstreamBinding) -> None:
        self.journal = journal
        self.binding = binding
        self.initial_cursor = AcceptedCoordinatorCursor.initial(binding)

    def read_after(self, cursor: AcceptedCoordinatorCursor) -> CampaignLayoutBatch:
        history, fresh = _verified_history(
            self.journal, self.binding, cursor, owner_kind="COORDINATOR"
        )
        if not history:
            return CampaignLayoutBatch((), _next_cursor(history, self.binding), {}, "")
        if _journal_format(history) != _CANONICAL:
            # This layout is the canonical campaign stream by definition; a legacy journal under
            # the campaign name is not the same producer and is never merged as if it were.
            raise CoordinatorProjectionError("CAMPAIGN_JOURNAL_FORMAT")
        if history[0].type != "CAMPAIGN_STARTED":
            raise CoordinatorProjectionError("CAMPAIGN_START_INVALID")
        start = history[0].payload
        campaign_id = _require_id("campaign_id", start.get("campaign_id"))
        if (
            _require_id("batch_id", start.get("batch_id")) != self.binding.batch_id
            or campaign_id != self.binding.campaign_id
        ):
            raise CoordinatorProjectionError("CAMPAIGN_START_INVALID")
        binding_document = read_selection_binding(self.binding)
        terminals = _terminal_index(history)

        reducer = CanonicalCampaignReducer(identity_required=False)
        state = None
        translated: list[UpstreamEventView] = []
        for event in history:
            canonical = self._canonical_event(event, binding_document, terminals)
            translated.append(canonical)
            try:
                state = reducer.apply(state, canonical)
            except ReducerError as error:
                raise CoordinatorProjectionError(str(error)) from error
        # The batch carries the *translated* events in the batch's own order: the projection and
        # the store's transaction both reduce these, never the raw campaign payloads, so the
        # committed state and the projected state can never be derived differently.
        fresh_translated = translated[len(translated) - len(fresh):] if fresh else []
        return CampaignLayoutBatch(
            events=tuple(fresh_translated),
            next_cursor=_next_cursor(history, self.binding),
            projected_state={} if state is None else projection_document(state),
            campaign_id=campaign_id,
        )

    def _canonical_event(self, event, binding_document, terminals) -> UpstreamEventView:
        """Translate one campaign event, or refuse the projection."""

        payload = event.payload
        event_type = event.type
        if event_type not in _TRANSLATED_EVENT_TYPES:
            raise CoordinatorProjectionError(f"CAMPAIGN_EVENT_UNSUPPORTED:{event_type}")
        translated: dict[str, object] = {}
        if event_type == "CAMPAIGN_STARTED":
            translated = {
                "campaign_id": _require_id("campaign_id", payload.get("campaign_id")),
                "batch_id": _require_id("batch_id", payload.get("batch_id")),
                # The config hash is the batch's own binding document, already verified above.
                "config_sha256": binding_document["config_sha256"],
            }
        elif event_type in {"POINT_LEASED", "ATTEMPT_STARTED", "WORKER_REGISTERED"}:
            translated = {
                "point_id": _require_id("point_id", payload.get("point_id")),
                "attempt_id": _require_id("attempt_id", payload.get("attempt_id")),
            }
            for name in ("worker_id", "slot_id"):
                if isinstance(payload.get(name), str) and payload[name]:
                    translated[name] = payload[name]
            generation = _require_optional_int("generation", payload.get("generation"))
            if generation is not None:
                translated["worker_generation"] = generation
                translated["lease_generation"] = generation
            if event_type == "POINT_LEASED":
                selection_sha256 = payload.get("selection_sha256")
                if selection_sha256 != binding_document["selection_sha256"]:
                    # The lease was issued from another selection than this batch's binding.
                    raise CoordinatorProjectionError("CAMPAIGN_BINDING_INVALID")
        elif event_type == "RESULT_COMMITTED":
            point_id = _require_id("point_id", payload.get("point_id"))
            attempt_id = _require_id("attempt_id", payload.get("attempt_id"))
            outcome = _require_id("outcome", payload.get("outcome"))
            terminal = terminals.get((point_id, attempt_id))
            if terminal is None or terminal[0] != outcome:
                # No committed terminal for this result: the hash is unknown, and unknown is not
                # a value this adapter is allowed to make up.
                raise CoordinatorProjectionError("CAMPAIGN_RESULT_HASH_MISSING")
            _point_result_document(self.binding, payload, point_id, attempt_id, outcome)
            translated = {
                "point_id": point_id,
                "attempt_id": attempt_id,
                "outcome": outcome,
                "result_sha256": terminal[1],
            }
            for name in ("worker_id", "slot_id"):
                if isinstance(payload.get(name), str) and payload[name]:
                    translated[name] = payload[name]
            generation = _require_optional_int("generation", payload.get("generation"))
            if generation is not None:
                translated["worker_generation"] = generation
                translated["lease_generation"] = generation
        elif event_type == "POINT_TERMINAL":
            point_id = _require_id("point_id", payload.get("point_id"))
            attempt_id = _require_id("attempt_id", payload.get("attempt_id"))
            terminal = terminals.get((point_id, attempt_id))
            if terminal is None:
                raise CoordinatorProjectionError("CAMPAIGN_TERMINAL_INVALID")
            translated = {
                "point_id": point_id,
                "attempt_id": attempt_id,
                "result_sha256": terminal[1],
            }
        elif event_type == "BATCH_TERMINAL":
            verdict = _require_id("outcome", payload.get("outcome"))
            translated = {
                "business_terminal": (
                    POINTS_COMPLETE if verdict in _CAMPAIGN_PASS_VERDICTS else verdict
                ),
            }
        else:  # CLEANUP_COMMITTED
            cleanup_complete = payload.get("cleanup_complete", True)
            if not isinstance(cleanup_complete, bool):
                raise CoordinatorProjectionError("CAMPAIGN_CLEANUP_INVALID")
            translated = {"cleanup_complete": cleanup_complete}
        return UpstreamEventView(
            batch_id=self.binding.batch_id,
            type=event_type,
            idempotency_key=event.idempotency_key,
            payload=translated,
            owner_epoch=event.coordinator_epoch,
            sequence=event.sequence,
            previous_frame_sha256=event.prev_frame_sha256,
            frame_sha256=event.frame_sha256,
        )


def campaign_committed_attempt(event, binding: CampaignUpstreamBinding) -> CommittedAttemptEvidence:
    """The verified identity of one campaign result, with no artifact import.

    The campaign layout writes no sealed ``attempt_result_manifest.json``, so no artifact may be
    registered here. The result itself was already verified by ``CampaignLayoutReader`` against the
    journal's own terminal and the batch's durable per-point document, and the identity is read
    from those same committed fields rather than invented.
    """

    payload = event.payload
    point_id = _require_id("point_id", payload.get("point_id"))
    attempt_id = _require_id("attempt_id", payload.get("attempt_id"))
    worker_id = _require_id("worker_id", payload.get("worker_id"))
    generation = _require_optional_int("generation", payload.get("generation")) or 1
    worker_generation = _require_optional_int(
        "worker_generation", payload.get("worker_generation")
    ) or generation
    return CommittedAttemptEvidence(
        identity=AttemptIdentity(
            batch_id=binding.batch_id,
            coordinator_epoch=event.owner_epoch,
            worker_id=worker_id,
            worker_generation=worker_generation,
            point_id=point_id,
            attempt_id=attempt_id,
            lease_generation=generation,
        ),
        status=_require_id("outcome", payload.get("outcome")),
        artifacts=(),
    )
