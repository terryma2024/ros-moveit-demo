"""Read-only projection of the fixed coordinator's verified journal."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Callable, Literal, Mapping

from so101_demo.parallel_batch.journal import (
    CoordinatorJournal,
    JournalCorruption,
    JournalEvent,
)


@dataclass(frozen=True, slots=True)
class ReadOnlyCoordinatorJournal:
    root: Path
    batch_id: str

    def replay(self):
        return CoordinatorJournal.read_only_replay(self.root, self.batch_id)


class CoordinatorProjectionError(RuntimeError):
    """A bound journal or referenced committed result failed closed."""


@dataclass(frozen=True, slots=True)
class CampaignUpstreamBinding:
    campaign_id: str
    batch_id: str
    owner_kind: Literal["COORDINATOR", "ADAPTIVE_RUNNER"]
    owner_epoch_or_generation: int
    journal_root: Path
    batch_root: Path

    def __post_init__(self) -> None:
        if not self.campaign_id or not self.batch_id:
            raise ValueError("BINDING_ID_REQUIRED")
        if self.owner_kind not in {"COORDINATOR", "ADAPTIVE_RUNNER"}:
            raise ValueError("BINDING_OWNER_KIND")
        if self.owner_epoch_or_generation <= 0:
            raise ValueError("BINDING_OWNER_EPOCH")
        for field_name in ("journal_root", "batch_root"):
            value = Path(getattr(self, field_name))
            if not value.is_absolute():
                raise ValueError("BINDING_ABSOLUTE_PATH")
            object.__setattr__(self, field_name, value.resolve())


@dataclass(frozen=True, slots=True)
class AcceptedCoordinatorCursor:
    batch_id: str
    owner_epoch_or_generation: int
    sequence: int
    frame_sha256: str | None

    @classmethod
    def initial(cls, binding: CampaignUpstreamBinding) -> AcceptedCoordinatorCursor:
        return cls(
            binding.batch_id,
            binding.owner_epoch_or_generation,
            0,
            None,
        )


@dataclass(frozen=True, slots=True)
class UpstreamEventView:
    batch_id: str
    type: str
    idempotency_key: str
    payload: Mapping[str, object]
    owner_epoch: int
    sequence: int
    previous_frame_sha256: str
    frame_sha256: str


@dataclass(frozen=True, slots=True)
class CoordinatorEventBatch:
    events: tuple[UpstreamEventView, ...]
    next_cursor: AcceptedCoordinatorCursor
    projected_point_states: Mapping[str, str]
    projected_state: Mapping[str, object]


ManifestVerifier = Callable[[Mapping[str, object], CampaignUpstreamBinding], None]


def verify_event_binding(
    event: JournalEvent,
    binding: CampaignUpstreamBinding,
) -> None:
    if event.coordinator_epoch > binding.owner_epoch_or_generation:
        raise CoordinatorProjectionError("OWNER_EPOCH_MISMATCH")
    if event.sequence <= 0 or not event.frame_sha256:
        raise CoordinatorProjectionError("EVENT_IDENTITY_INVALID")


def _verify_reader_binding(journal, binding: CampaignUpstreamBinding, owner_kind: str) -> None:
    if binding.owner_kind != owner_kind:
        raise CoordinatorProjectionError("OWNER_KIND_MISMATCH")
    if getattr(journal, "batch_id", None) != binding.batch_id:
        raise CoordinatorProjectionError("JOURNAL_BATCH_MISMATCH")
    journal_root = Path(getattr(journal, "root", "")).resolve()
    if journal_root != binding.journal_root:
        raise CoordinatorProjectionError("JOURNAL_ROOT_MISMATCH")


def _verified_history(
    journal,
    binding: CampaignUpstreamBinding,
    cursor: AcceptedCoordinatorCursor,
    *,
    owner_kind: str,
) -> tuple[tuple[JournalEvent, ...], tuple[JournalEvent, ...]]:
    _verify_reader_binding(journal, binding, owner_kind)
    if cursor.batch_id != binding.batch_id:
        raise CoordinatorProjectionError("CURSOR_BATCH_MISMATCH")
    if cursor.owner_epoch_or_generation != binding.owner_epoch_or_generation:
        raise CoordinatorProjectionError("CURSOR_OWNER_MISMATCH")
    try:
        history = tuple(journal.replay().events)
    except JournalCorruption as error:
        if str(error) == "incomplete journal tail":
            raise CoordinatorProjectionError("JOURNAL_REPLAY_INCOMPLETE") from error
        raise CoordinatorProjectionError("JOURNAL_REPLAY_INVALID") from error
    except (OSError, RuntimeError, ValueError) as error:
        raise CoordinatorProjectionError("JOURNAL_REPLAY_INVALID") from error
    for expected_sequence, event in enumerate(history, start=1):
        verify_event_binding(event, binding)
        if event.sequence != expected_sequence:
            raise CoordinatorProjectionError("EVENT_SEQUENCE_GAP")
    if cursor.sequence < 0 or cursor.sequence > len(history):
        raise CoordinatorProjectionError("CURSOR_AHEAD")
    if cursor.sequence:
        accepted = history[cursor.sequence - 1]
        if accepted.frame_sha256 != cursor.frame_sha256:
            raise CoordinatorProjectionError("CURSOR_HASH_MISMATCH")
    elif cursor.frame_sha256 is not None:
        raise CoordinatorProjectionError("CURSOR_HASH_MISMATCH")
    return history, history[cursor.sequence :]


def _event_view(event: JournalEvent, batch_id: str) -> UpstreamEventView:
    return UpstreamEventView(
        batch_id=batch_id,
        type=event.type,
        idempotency_key=event.idempotency_key,
        payload=event.payload,
        owner_epoch=event.coordinator_epoch,
        sequence=event.sequence,
        previous_frame_sha256=event.prev_frame_sha256,
        frame_sha256=event.frame_sha256,
    )


def _next_cursor(
    history: tuple[JournalEvent, ...], binding: CampaignUpstreamBinding
) -> AcceptedCoordinatorCursor:
    if not history:
        return AcceptedCoordinatorCursor.initial(binding)
    final = history[-1]
    return AcceptedCoordinatorCursor(
        binding.batch_id,
        binding.owner_epoch_or_generation,
        final.sequence,
        final.frame_sha256,
    )


def _default_manifest_verifier(
    reference: Mapping[str, object], binding: CampaignUpstreamBinding
) -> None:
    location = reference.get("location")
    digest = reference.get("sha256")
    if not isinstance(location, str) or not isinstance(digest, str):
        raise CoordinatorProjectionError("RESULT_REFERENCE_INVALID")
    path = Path(location)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(binding.batch_root)
    except (OSError, ValueError) as error:
        raise CoordinatorProjectionError("RESULT_REFERENCE_OUTSIDE_BATCH") from error
    if path.is_symlink():
        raise CoordinatorProjectionError("RESULT_REFERENCE_INVALID")
    manifest = resolved
    if resolved.is_dir():
        manifest = resolved / "attempt_result_manifest.json"
        if manifest.is_symlink() or not manifest.is_file():
            raise CoordinatorProjectionError("RESULT_REFERENCE_INVALID")
    elif not resolved.is_file():
        raise CoordinatorProjectionError("RESULT_REFERENCE_INVALID")
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != digest:
        raise CoordinatorProjectionError("RESULT_REFERENCE_HASH_MISMATCH")


def _merge_projection_delta(state: dict[str, object], delta: Mapping[str, object]) -> None:
    for key, value in delta.items():
        if not isinstance(key, str):
            raise CoordinatorProjectionError("PROJECTION_DELTA_INVALID")
        if key in {"points", "workers"}:
            if not isinstance(value, Mapping):
                raise CoordinatorProjectionError("PROJECTION_DELTA_INVALID")
            collection = state.setdefault(key, {})
            if not isinstance(collection, dict):
                raise CoordinatorProjectionError("PROJECTION_DELTA_INVALID")
            for item_id, item_delta in value.items():
                if not isinstance(item_id, str) or not isinstance(item_delta, Mapping):
                    raise CoordinatorProjectionError("PROJECTION_DELTA_INVALID")
                item = collection.setdefault(item_id, {})
                if not isinstance(item, dict):
                    raise CoordinatorProjectionError("PROJECTION_DELTA_INVALID")
                item.update(deepcopy(dict(item_delta)))
        else:
            state[key] = deepcopy(value)



#: The canonical campaign vocabulary. A journal is either canonical or legacy, never both: the
#: canonical stream is the durable contract the coordinator publishes and the only input the
#: reducer accepts.
#:
#: `POINT_LEASED`, `CAMPAIGN_STARTED`, `POINT_TERMINAL` and `CLEANUP_COMMITTED` exist only in the
#: canonical vocabulary, and `BATCH_STARTED`, `LEASE_GRANTED` and the other snapshot events exist
#: only in the legacy one. `ATTEMPT_STARTED` and `RESULT_COMMITTED` are shared names: in a
#: canonical journal they must carry canonical fields.
_CANONICAL_ONLY_EVENT_TYPES = frozenset(
    {"CAMPAIGN_STARTED", "POINT_LEASED", "POINT_TERMINAL", "CLEANUP_COMMITTED"}
)
_LEGACY_ONLY_EVENT_TYPES = frozenset(
    {
        "BATCH_STARTED",
        "BATCH_MANIFEST",
        "POOL_STARTING",
        "LEASE_GRANTED",
        "BATCH_STOPPING",
        "BATCH_CLEANUP_COMPLETE",
        "POINT_RESULT_IMPORTED",
    }
)
_CANONICAL = "CANONICAL"
_LEGACY = "LEGACY"


def _journal_format(history) -> str:
    """Classify the journal, failing closed if canonical and legacy frames are mixed."""

    canonical = any(event.type in _CANONICAL_ONLY_EVENT_TYPES for event in history)
    legacy = any(event.type in _LEGACY_ONLY_EVENT_TYPES for event in history)
    if canonical and legacy:
        raise CoordinatorProjectionError("JOURNAL_FORMAT_MIXED")
    return _CANONICAL if canonical else _LEGACY


def _canonical_event(view: UpstreamEventView):
    """Adapt one verified canonical view, or return ``None`` for a non-campaign event.

    The adapter reads canonical fields only. A ``payload.delta`` is never read: a status that
    exists only in a delta is not evidence.
    """

    payload = view.payload
    event_type = view.type
    flat: dict[str, object] = {}
    if event_type == "CAMPAIGN_STARTED":
        for name in ("campaign_id", "batch_id", "runtime_identity_sha256", "config_sha256"):
            value = payload.get(name)
            if not isinstance(value, str) or not value:
                raise CoordinatorProjectionError("CAMPAIGN_START_INVALID")
            flat[name] = value
    elif event_type in {"POINT_LEASED", "ATTEMPT_STARTED", "RESULT_COMMITTED", "POINT_TERMINAL"}:
        point_id = payload.get("point_id")
        if not isinstance(point_id, str) or not point_id:
            return None
        flat["point_id"] = point_id
        attempt_id = payload.get("attempt_id")
        if isinstance(attempt_id, str) and attempt_id:
            flat["attempt_id"] = attempt_id
        if event_type != "POINT_TERMINAL" and "attempt_id" not in flat:
            raise CoordinatorProjectionError("EVENT_ATTEMPT_ID_REQUIRED")
        for name in ("worker_id", "slot_id"):
            value = payload.get(name)
            if isinstance(value, str) and value:
                flat[name] = value
        for name in ("worker_generation", "lease_generation"):
            value = payload.get(name)
            if type(value) is int and value > 0:
                flat[name] = value
        if event_type == "RESULT_COMMITTED":
            outcome = payload.get("outcome")
            result_sha256 = payload.get("result_sha256")
            if not isinstance(outcome, str) or not isinstance(result_sha256, str):
                raise CoordinatorProjectionError("RESULT_COMMIT_INCOMPLETE")
            flat["outcome"] = outcome
            flat["result_sha256"] = result_sha256
            validity = payload.get("attempt_validity")
            if isinstance(validity, str):
                flat["attempt_validity"] = validity
        if event_type == "POINT_TERMINAL":
            result_sha256 = payload.get("result_sha256")
            if not isinstance(result_sha256, str):
                raise CoordinatorProjectionError("RESULT_COMMIT_INCOMPLETE")
            flat["result_sha256"] = result_sha256
    elif event_type == "CLEANUP_COMMITTED":
        flat["cleanup_complete"] = bool(payload.get("cleanup_complete", True))
    elif event_type == "BATCH_TERMINAL":
        business = payload.get("business_terminal")
        infrastructure = payload.get("infrastructure_terminal")
        if business is not None:
            flat["business_terminal"] = str(business)
        if infrastructure is not None:
            flat["infrastructure_terminal"] = str(infrastructure)
    elif event_type != "WORKER_REGISTERED":
        return None
    return UpstreamEventView(
        batch_id=view.batch_id,
        type=event_type,
        idempotency_key=view.idempotency_key,
        payload=flat,
        owner_epoch=view.owner_epoch,
        sequence=view.sequence,
        previous_frame_sha256=view.previous_frame_sha256,
        frame_sha256=view.frame_sha256,
    )


def _reduce_canonical(history, binding, manifest_verifier, batch_id):
    from .reducer import CanonicalCampaignReducer, ReducerError, projection_document

    reducer = CanonicalCampaignReducer()
    reduced = None
    for event in history:
        payload = event.payload
        if event.type in {"RESULT_COMMITTED", "VALIDATION_COMMITTED"}:
            response = payload.get("response")
            if not isinstance(response, Mapping):
                raise CoordinatorProjectionError("RESULT_REFERENCE_INVALID")
            manifest_verifier(response, binding)
        canonical = _canonical_event(_event_view(event, batch_id))
        if canonical is None:
            continue
        try:
            reduced = reducer.apply(reduced, canonical)
        except ReducerError as error:
            raise CoordinatorProjectionError(str(error)) from error
    if reduced is None:
        return {}, {}
    projected_state = projection_document(reduced)
    point_states = {
        point_id: str(point["status"])
        for point_id, point in projected_state["points"].items()
    }
    return projected_state, point_states


class CoordinatorEventReader:
    """Project only verified coordinator commits for one durable binding."""

    def __init__(
        self,
        journal,
        binding: CampaignUpstreamBinding,
        *,
        manifest_verifier: ManifestVerifier | None = None,
    ) -> None:
        _verify_reader_binding(journal, binding, "COORDINATOR")
        self.journal = journal
        self.binding = binding
        self.manifest_verifier = manifest_verifier or _default_manifest_verifier
        self.initial_cursor = AcceptedCoordinatorCursor.initial(binding)

    def read_after(self, cursor: AcceptedCoordinatorCursor) -> CoordinatorEventBatch:
        history, fresh = _verified_history(
            self.journal,
            self.binding,
            cursor,
            owner_kind="COORDINATOR",
        )
        if _journal_format(history) == _CANONICAL:
            projected_state, point_states = _reduce_canonical(
                history, self.binding, self.manifest_verifier, self.binding.batch_id
            )
            return CoordinatorEventBatch(
                events=tuple(_event_view(event, self.binding.batch_id) for event in fresh),
                next_cursor=_next_cursor(history, self.binding),
                projected_point_states=point_states,
                projected_state=projected_state,
            )
        projected_state: dict[str, object] = {}
        for event in history:
            payload = event.payload
            if event.type in {"RESULT_COMMITTED", "VALIDATION_COMMITTED"}:
                response = payload.get("response")
                if not isinstance(response, Mapping):
                    raise CoordinatorProjectionError("RESULT_REFERENCE_INVALID")
                self.manifest_verifier(response, self.binding)
            delta = payload.get("delta")
            if not isinstance(delta, Mapping):
                continue
            _merge_projection_delta(projected_state, delta)
        point_states: dict[str, str] = {}
        points = projected_state.get("points", {})
        if not isinstance(points, Mapping):
            raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
        for point_id, point in points.items():
            if not isinstance(point_id, str) or not isinstance(point, Mapping):
                raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
            status = point.get("status") or point.get("validation_status")
            if status is not None:
                if not isinstance(status, str):
                    raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
                point_states[point_id] = status
        return CoordinatorEventBatch(
            events=tuple(_event_view(event, self.binding.batch_id) for event in fresh),
            next_cursor=_next_cursor(history, self.binding),
            projected_point_states=point_states,
            projected_state=projected_state,
        )
