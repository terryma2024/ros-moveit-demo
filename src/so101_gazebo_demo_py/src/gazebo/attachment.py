"""Durable reduction and convergent control of DetachableJoint events."""

import threading
import time
from typing import Protocol

from ..domain import ActionResult, ActionStatus, Failure, FailureCategory


class EmptyPublisher(Protocol):
    def publish_empty(self, topic: str) -> bool: ...


class AttachmentStateReducer:
    def __init__(self) -> None:
        self._state: str | None = None
        self._condition = threading.Condition()

    @property
    def state(self) -> str | None:
        with self._condition:
            return self._state

    def accept(self, event: str) -> bool:
        normalized = event.strip().strip('"').lower()
        if normalized not in ("attached", "detached"):
            return False
        with self._condition:
            self._state = normalized
            self._condition.notify_all()
        return True

    def wait_for(self, requested: str, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while self._state != requested:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True


class GazeboAttachmentClient:
    def __init__(
        self, transport: EmptyPublisher, reducer: AttachmentStateReducer,
        attach_topic: str, detach_topic: str,
    ) -> None:
        self.transport = transport
        self.reducer = reducer
        self.attach_topic = attach_topic
        self.detach_topic = detach_topic

    def set_attached(self, attached: bool, timeout_s: float) -> ActionResult:
        requested = "attached" if attached else "detached"
        topic = self.attach_topic if attached else self.detach_topic
        if not self.transport.publish_empty(topic):
            return ActionResult(
                ActionStatus.FAILED,
                Failure(FailureCategory.GAZEBO_ATTACHMENT, "GAZEBO_ATTACHMENT_PUBLISH_FAILED", f"cannot publish {topic}"),
            )
        if not self.reducer.wait_for(requested, timeout_s):
            return ActionResult(
                ActionStatus.TIMED_OUT,
                Failure(
                    FailureCategory.GAZEBO_ATTACHMENT,
                    "GAZEBO_ATTACHMENT_CONVERGENCE_TIMEOUT",
                    f"did not observe durable {requested} state",
                ),
            )
        return ActionResult(ActionStatus.SUCCEEDED)
