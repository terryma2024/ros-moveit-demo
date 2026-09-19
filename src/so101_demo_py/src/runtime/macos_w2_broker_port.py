"""The Worker-side Broker port for the macOS W2 campaign: permission-only, generation-checked.

This is the v4 port of `cli/mujoco_parallel_batch._WorkerBrokerProxy`. Two things differ, and both
follow from schema v4 rather than from taste:

* the transport is `V4PermissionOnlyClient` - a `0600` socket under the Darwin private root, with no
  token, generation, lease or endpoint receipt in either direction;
* the generation bookkeeping stays local to the Worker: the Coordinator's authority document is the
  only place a generation is read, and it may only move forward.

Everything else keeps the production proxy's contract, so a Worker runtime written against the
container path keeps working here: `request_model` refreshes the authority (without waiting for
health) and then runs the perception chain, while `cancel_generation` waits for the Broker to be
healthy before it sends the one cancellation message.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable, Mapping

from .parallel_ipc_v4 import V4PermissionOnlyClient


class W2BrokerPortError(RuntimeError):
    """The port cannot serve a request under its current authority."""


@dataclass(frozen=True, slots=True)
class BrokerAuthority:
    """The Coordinator's answer about the owned Broker, reduced to what a Worker may act on."""

    healthy: bool
    generation: int
    endpoint_path: str


class W2BrokerPort:
    """One Worker's permission-only channel to the shared MPS Broker."""

    def __init__(
        self,
        *,
        coordinator,
        authority: BrokerAuthority,
        config,
        client_factory: Callable[..., object] = V4PermissionOnlyClient,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        connection=None,
    ) -> None:
        if not isinstance(authority, BrokerAuthority):
            raise TypeError("a BrokerAuthority is required")
        if type(authority.generation) is not int or authority.generation <= 0:
            raise W2BrokerPortError("BROKER_GENERATION_AUTHORITY")
        self.coordinator = coordinator
        self.config = config
        self.broker_generation = authority.generation
        self._client_factory = client_factory
        self._clock = clock
        self._sleep = sleep
        self.connection = connection

    def _connect(self, authority: BrokerAuthority):
        return self._client_factory(
            endpoint_path=authority.endpoint_path,
            max_frame_bytes=self.config.broker_max_frame_bytes,
            io_timeout_s=self.config.executing_hard_timeout_s,
        )

    def _adopt(self, authority: BrokerAuthority) -> None:
        """Adopt a newer generation, or fail closed if the authority went backwards."""

        if not isinstance(authority, BrokerAuthority):
            raise W2BrokerPortError("BROKER_AUTHORITY_INVALID")
        if authority.generation < self.broker_generation:
            raise W2BrokerPortError("BROKER_GENERATION_ROLLBACK")
        if authority.generation != self.broker_generation or self.connection is None:
            self.connection = self._connect(authority)
            self.broker_generation = authority.generation

    def refresh(self, *, wait_until_healthy: bool) -> BrokerAuthority:
        """Read the Coordinator's authority; optionally wait for a healthy Broker.

        A Worker that is replaced must never keep talking to the old endpoint, so the client is
        rebuilt whenever the generation moves. Waiting is bounded by the configured recovery
        timeout rather than being open-ended.
        """

        deadline = self._clock() + float(self.config.broker_recovery_timeout_s)
        authority = self.coordinator()
        while wait_until_healthy and not authority.healthy:
            if self._clock() >= deadline:
                raise W2BrokerPortError("BROKER_RECOVERY_TIMEOUT")
            self._sleep(0.05)
            authority = self.coordinator()
        if not authority.healthy:
            raise W2BrokerPortError("BROKER_UNHEALTHY")
        self._adopt(authority)
        return authority

    def request_model(self, lease, execution_kind, *, snapshot, start_event_id,
                      start_event_type, reset_epoch, perception_runner=None) -> object:
        """Run one inference through the shared Broker and the Worker's perception chain.

        `perception_runner` is the port the Worker runtime supplies; the Broker response itself is
        never an outcome - only the chain that consumes it can admit a pose.
        """

        self.refresh(wait_until_healthy=False)
        if perception_runner is None:
            raise W2BrokerPortError("PERCEPTION_RUNNER_REQUIRED")
        return perception_runner(
            lease=lease,
            execution_kind=execution_kind,
            snapshot=snapshot,
            start_event_id=start_event_id,
            start_event_type=start_event_type,
            reset_epoch=reset_epoch,
            connection=self.connection,
            broker_generation=self.broker_generation,
        )

    def cancel_generation(self, worker_id: str, generation: int) -> bool:
        """Cancel one generation on the Broker, after it is healthy enough to answer.

        `ParallelWorker` fences on `cancel_generation(...) is True`, so this answers the boolean the
        lease logic asks for; a refusal that cannot reach the Broker raises instead of returning a
        false fence.
        """

        self.refresh(wait_until_healthy=True)
        self.connection.call(
            "cancel_generation",
            {"worker_id": worker_id, "worker_generation": generation},
        )
        return True


def authority_from_document(document: Mapping[str, object]) -> BrokerAuthority:
    """Reduce a Coordinator authority document to the fields a Worker is allowed to act on."""

    if not isinstance(document, Mapping):
        raise W2BrokerPortError("BROKER_AUTHORITY_INVALID")
    try:
        healthy = bool(document["healthy"])
        generation = document["broker_generation"]
        endpoint_path = str(document["broker_socket_path"])
    except KeyError as error:
        raise W2BrokerPortError(f"BROKER_AUTHORITY_INCOMPLETE: {error}") from error
    if type(generation) is not int or generation <= 0:
        raise W2BrokerPortError("BROKER_GENERATION_AUTHORITY")
    if not endpoint_path:
        raise W2BrokerPortError("BROKER_ENDPOINT_MISSING")
    return BrokerAuthority(healthy=healthy, generation=generation, endpoint_path=endpoint_path)
