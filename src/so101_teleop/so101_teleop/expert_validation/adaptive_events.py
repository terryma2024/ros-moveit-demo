"""Read-only projection of the adaptive Runner's top-level journal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .coordinator_events import (
    AcceptedCoordinatorCursor,
    CampaignUpstreamBinding,
    UpstreamEventView,
    _event_view,
    _next_cursor,
    _verified_history,
    _verify_reader_binding,
)


@dataclass(frozen=True, slots=True)
class AdaptivePointView:
    point_id: str
    status: str
    infra_attempts: int = 0
    evidence_root: str | None = None


@dataclass(frozen=True, slots=True)
class AdaptiveFallbackView:
    generation: int
    from_count: int
    to_count: int
    reason: str

    @property
    def transition(self) -> str:
        return f"W{self.from_count}_TO_W{self.to_count}"


@dataclass(frozen=True, slots=True)
class AdaptiveProjection:
    current_level: int | None
    current_generation: int | None
    levels_used: tuple[int, ...]
    fallbacks: tuple[AdaptiveFallbackView, ...]
    points: Mapping[str, AdaptivePointView]
    terminal_status: str | None
    cleanup_complete: bool | None


@dataclass(frozen=True, slots=True)
class AdaptiveEventBatch:
    events: tuple[UpstreamEventView, ...]
    next_cursor: AcceptedCoordinatorCursor
    projection: AdaptiveProjection


class AdaptiveEventReader:
    """Consume only the Runner journal, never nested coordinator journals."""

    def __init__(self, journal, binding: CampaignUpstreamBinding) -> None:
        _verify_reader_binding(journal, binding, "ADAPTIVE_RUNNER")
        self.journal = journal
        self.binding = binding
        self.initial_cursor = AcceptedCoordinatorCursor.initial(binding)

    def read_after(self, cursor: AcceptedCoordinatorCursor) -> AdaptiveEventBatch:
        history, fresh = _verified_history(
            self.journal,
            self.binding,
            cursor,
            owner_kind="ADAPTIVE_RUNNER",
        )
        points: dict[str, AdaptivePointView] = {}
        levels: list[int] = []
        fallbacks: list[AdaptiveFallbackView] = []
        current_level = None
        current_generation = None
        terminal_status = None
        cleanup_complete = None
        for event in history:
            payload = event.payload
            if event.type == "BATCH_MANIFEST":
                selected = payload.get("selected_point_ids")
                if isinstance(selected, list):
                    for point_id in selected:
                        if isinstance(point_id, str):
                            points[point_id] = AdaptivePointView(point_id, "UNRUN")
            elif event.type == "POOL_STARTING":
                current_level = int(payload["worker_count"])
                current_generation = int(payload["generation"])
                if current_level not in levels:
                    levels.append(current_level)
            elif event.type == "POOL_RUNNING":
                current_level = int(payload["worker_count"])
                current_generation = int(payload["generation"])
            elif event.type == "POINT_INFRA_INTERRUPTED":
                point_id = str(payload["point_id"])
                points[point_id] = AdaptivePointView(
                    point_id,
                    "INFRA_INTERRUPTED",
                    int(payload["infra_attempts"]),
                )
            elif event.type == "POINT_RESULT_IMPORTED":
                result = payload["result"]
                point_id = str(result["point_id"])
                points[point_id] = AdaptivePointView(
                    point_id,
                    str(result["status"]),
                    int(result["infra_attempts"]),
                    str(result["evidence_root"]),
                )
            elif event.type == "POOL_DEGRADED":
                failure = payload["failure"]
                fallbacks.append(
                    AdaptiveFallbackView(
                        generation=int(payload["generation"]),
                        from_count=int(payload["from_count"]),
                        to_count=int(payload["to_count"]),
                        reason=str(failure["kind"]),
                    )
                )
            elif event.type == "BATCH_TERMINAL":
                terminal_status = str(payload["status"])
                cleanup_complete = bool(payload["cleanup_complete"])
        return AdaptiveEventBatch(
            events=tuple(_event_view(event, self.binding.batch_id) for event in fresh),
            next_cursor=_next_cursor(history, self.binding),
            projection=AdaptiveProjection(
                current_level=current_level,
                current_generation=current_generation,
                levels_used=tuple(levels),
                fallbacks=tuple(fallbacks),
                points=points,
                terminal_status=terminal_status,
                cleanup_complete=cleanup_complete,
            ),
        )
