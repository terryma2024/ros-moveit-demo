"""The execution profile, single-worker constants and the approved execution routes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from so101_demo.parallel_batch.contracts.common import ContractError
from so101_demo.parallel_batch.contracts.linux_cuda import BatchKind
from so101_demo.parallel_batch.contracts.macos_two_worker import (
    EXECUTION_MACOS_MPS_TWO_WORKER_FIELDS,
    FROZEN_DARWIN_VALUES_MACOS_MPS_TWO_WORKER,
    FROZEN_RUNTIME_VALUES_MACOS_MPS_TWO_WORKER,
    MACOS_MPS_TWO_WORKER_CONFIG_FIELDS,
    MACOS_MPS_TWO_WORKER_PLATFORM_WORKER_COUNT,
    START_GUARD_MACOS_MPS_TWO_WORKER_FIELDS,
)


class ExecutionProfile(StrEnum):
    """The closed set of approved macOS execution profiles."""

    MPS_TWO_WORKER_FIRST_PASS = "MPS_TWO_WORKER_FIRST_PASS"
    MPS_SINGLE_WORKER_FULL_RESTART_RETRY = "MPS_SINGLE_WORKER_FULL_RESTART_RETRY"
    MPS_SINGLE_WORKER_FIRST_PASS = "MPS_SINGLE_WORKER_FIRST_PASS"


#: The only worker counts the single-worker profiles support. single-worker is a platform claim, not a shrunken two-worker.
MACOS_MPS_SINGLE_WORKER_RETRY_PLATFORM_WORKER_COUNT = 1


MACOS_MPS_SINGLE_WORKER_FIRST_PASS_PLATFORM_WORKER_COUNT = 1


#: The single-worker profiles admit exactly one platform combination: the Darwin MPS one.
SINGLE_WORKER_PLATFORM_COMBINATIONS: tuple[tuple[str, str, str, str], ...] = (
    ("mps", "mps", "darwin_private_path_unix", "cgl"),
)


#: v5 and v6 restate the v4 freeze with their own schema and worker count. They add no field and
#: redefine no functional value: the shape is the v4 shape at single-worker.
FROZEN_RUNTIME_VALUES_MACOS_MPS_SINGLE_WORKER_RETRY: Mapping[str, object] = MappingProxyType({
    **FROZEN_RUNTIME_VALUES_MACOS_MPS_TWO_WORKER,
    "schema_version": 5,
    "worker_count": MACOS_MPS_SINGLE_WORKER_RETRY_PLATFORM_WORKER_COUNT,
})


FROZEN_RUNTIME_VALUES_MACOS_MPS_SINGLE_WORKER_FIRST_PASS: Mapping[str, object] = MappingProxyType({
    **FROZEN_RUNTIME_VALUES_MACOS_MPS_TWO_WORKER,
    "schema_version": 6,
    "worker_count": MACOS_MPS_SINGLE_WORKER_FIRST_PASS_PLATFORM_WORKER_COUNT,
})


#: The Darwin pins are shared by all three approved profiles.
FROZEN_DARWIN_VALUES_MACOS_MPS_SINGLE_WORKER_RETRY: Mapping[str, object] = FROZEN_DARWIN_VALUES_MACOS_MPS_TWO_WORKER


FROZEN_DARWIN_VALUES_MACOS_MPS_SINGLE_WORKER_FIRST_PASS: Mapping[str, object] = FROZEN_DARWIN_VALUES_MACOS_MPS_TWO_WORKER


MACOS_MPS_SINGLE_WORKER_RETRY_CONFIG_FIELDS = MACOS_MPS_TWO_WORKER_CONFIG_FIELDS


MACOS_MPS_SINGLE_WORKER_FIRST_PASS_CONFIG_FIELDS = MACOS_MPS_TWO_WORKER_CONFIG_FIELDS


EXECUTION_MACOS_MPS_SINGLE_WORKER_RETRY_FIELDS = EXECUTION_MACOS_MPS_TWO_WORKER_FIELDS


EXECUTION_MACOS_MPS_SINGLE_WORKER_FIRST_PASS_FIELDS = EXECUTION_MACOS_MPS_TWO_WORKER_FIELDS


START_GUARD_MACOS_MPS_SINGLE_WORKER_RETRY_FIELDS = START_GUARD_MACOS_MPS_TWO_WORKER_FIELDS


START_GUARD_MACOS_MPS_SINGLE_WORKER_FIRST_PASS_FIELDS = START_GUARD_MACOS_MPS_TWO_WORKER_FIELDS


@dataclass(frozen=True, slots=True)
class ExecutionRoute:
    """One admitted line of the support matrix."""

    schema_version: int
    execution_profile: ExecutionProfile
    batch_kind: BatchKind
    worker_count: int

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version not in (4, 5, 6):
            raise ContractError("SCHEMA_VERSION")
        try:
            object.__setattr__(self, "execution_profile", ExecutionProfile(self.execution_profile))
            object.__setattr__(self, "batch_kind", BatchKind(self.batch_kind))
        except ValueError as error:
            raise ContractError("EXECUTION_PROFILE_UNKNOWN") from error
        if isinstance(self.worker_count, bool) or self.worker_count not in (1, 2):
            raise ContractError("PLATFORM_WORKER_COUNT_UNSUPPORTED")

    @property
    def key(self) -> tuple[int, str, str, int]:
        """The dispatch key: schema, profile, batch kind, worker count."""

        return (self.schema_version, str(self.execution_profile), str(self.batch_kind),
                self.worker_count)


#: The whole support matrix. Three rows, no N>2 and no adaptive row.
APPROVED_EXECUTION_ROUTES: tuple[ExecutionRoute, ...] = (
    ExecutionRoute(schema_version=4, execution_profile=ExecutionProfile.MPS_TWO_WORKER_FIRST_PASS,
                   batch_kind=BatchKind.FIRST_PASS, worker_count=MACOS_MPS_TWO_WORKER_PLATFORM_WORKER_COUNT),
    ExecutionRoute(schema_version=5,
                   execution_profile=ExecutionProfile.MPS_SINGLE_WORKER_FULL_RESTART_RETRY,
                   batch_kind=BatchKind.FULL_RESTART_RETRY,
                   worker_count=MACOS_MPS_SINGLE_WORKER_RETRY_PLATFORM_WORKER_COUNT),
    ExecutionRoute(schema_version=6, execution_profile=ExecutionProfile.MPS_SINGLE_WORKER_FIRST_PASS,
                   batch_kind=BatchKind.FIRST_PASS, worker_count=MACOS_MPS_SINGLE_WORKER_FIRST_PASS_PLATFORM_WORKER_COUNT),
)


_ROUTE_BY_PROFILE: Mapping[ExecutionProfile, ExecutionRoute] = MappingProxyType({
    route.execution_profile: route for route in APPROVED_EXECUTION_ROUTES
})


_ROUTE_BY_SCHEMA: Mapping[int, ExecutionRoute] = MappingProxyType({
    route.schema_version: route for route in APPROVED_EXECUTION_ROUTES
})


def execution_route_for_schema(schema_version: object) -> ExecutionRoute:
    """The one approved route a schema version owns; every other version is refused."""

    if type(schema_version) is not int:
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")
    try:
        return _ROUTE_BY_SCHEMA[schema_version]
    except KeyError as error:
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION") from error


def resolve_execution_route(*, schema_version: object, execution_profile: object,
                            batch_kind: object, worker_count: object) -> ExecutionRoute:
    """Resolve the dispatch key against the closed support matrix, or refuse it by name.

    Every component is checked against the table rather than inferred. In particular a profile is
    never filled in from ``len(selected_point_ids)``: ``None`` is the shape such an inference
    produces and it is refused as :data:`PROFILE_FROM_SELECTED_POINTS`.
    """

    if execution_profile is None or worker_count is None:
        raise ContractError("PROFILE_FROM_SELECTED_POINTS")
    if type(schema_version) is not int or schema_version not in (4, 5, 6):
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")
    try:
        profile = ExecutionProfile(execution_profile)
    except (ValueError, TypeError) as error:
        raise ContractError("EXECUTION_PROFILE_UNKNOWN") from error
    route = _ROUTE_BY_PROFILE[profile]
    if route.schema_version != schema_version:
        # A v4 document claiming single-worker, a v5 document claiming first-pass or a v6 document claiming
        # retry all land here: the profile belongs to exactly one schema.
        raise ContractError("PROFILE_SCHEMA_MISMATCH")
    try:
        kind = BatchKind(batch_kind)
    except (ValueError, TypeError) as error:
        raise ContractError("BATCH_KIND_UNKNOWN") from error
    if kind is BatchKind.ADAPTIVE_POOL:
        raise ContractError("ADAPTIVE_UNSUPPORTED_ON_MACOS")
    if isinstance(worker_count, bool) or worker_count != route.worker_count:
        raise ContractError("PLATFORM_WORKER_COUNT_UNSUPPORTED")
    if kind is not route.batch_kind:
        raise ContractError("PROFILE_BATCH_KIND_MISMATCH")
    return route
