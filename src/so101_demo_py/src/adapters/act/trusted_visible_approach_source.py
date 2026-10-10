"""Broker-private source port for the first validated visible approach."""

import copy
import threading

from so101_demo.act.prefix_source import PrefixSourceAuthority

from .pick_place_search_native_ingress import native_ingress_digest
from .pick_place_search_port import PickPlaceSearchPhasePort
from .selected_search_source import freeze_selected_search_source
from .visible_approach_expert_route import VisibleApproachExpertRoute


class TrustedVisibleApproachSourcePort:
    """Register one current SEARCH source without granting a permit or goal."""

    def __init__(self):
        self._lock = threading.RLock()
        self._entry = None

    @staticmethod
    def _scope(broker, ticket, source):
        broker.ownership.require_ticket(ticket)
        epoch = broker.driver.current_epoch()
        if (ticket[2:] != ("act", source["session_id"], source["attempt_id"])
                or broker.simulation_session_id != source["session_id"]
                or broker._armed_generation != ticket[0]
                or broker.driver.stopped() is not True
                or type(epoch) is not dict
                or epoch.get("session_id") != source["session_id"]
                or epoch.get("reset_epoch") != source["reset_epoch"]):
            raise ValueError("VISIBLE_APPROACH_SOURCE_SCOPE_CHANGED")

    def register(self, broker, search_port, route, ticket, *,
                 active_policy_fingerprint):
        """Issue one broker-owned EXPERT_ROUTE receipt from actual SEARCH data."""
        try:
            with self._lock:
                if (self._entry is not None
                        or broker._prefix_source_port is not self
                        or not isinstance(broker._prefix_sources, PrefixSourceAuthority)
                        or broker.reservation_port is None
                        or not isinstance(search_port, PickPlaceSearchPhasePort)
                        or search_port._searched is not True
                        or not isinstance(route, VisibleApproachExpertRoute)):
                    raise ValueError("source port")
                observed = search_port.validated_search_observation()
                source = freeze_selected_search_source(
                    observed, max_skew_s=route.candidate.max_skew)
                native = observed.native_controller_ingress_proof
                if (type(native) is not dict
                        or native.get("native_ingress_window_sha256") !=
                           native_ingress_digest(native["native_snapshots"])):
                    raise ValueError("native ingress")
                self._scope(broker, ticket, source)
                prepared = route.prepare(
                    observed, selected_source=source, owner_ticket=ticket,
                    active_policy_fingerprint=active_policy_fingerprint)
                if (prepared["selected_source"] != source
                        or prepared["native_ingress_window_sha256"] !=
                           native["native_ingress_window_sha256"]
                        or prepared["command_authority"] is not False
                        or prepared["eligible_for_collection"] is not False):
                    raise ValueError("expert route")
                self._scope(broker, ticket, source)
                receipt = broker.issue_prefix_source(
                    ticket=ticket, prefix=prepared["prefix"], source=source,
                    source_kind="EXPERT_ROUTE",
                    source_artifact_sha256=prepared["source_artifact_sha256"],
                    contact_policy_fingerprint=prepared["policy_fingerprint"],
                )
                self._scope(broker, ticket, source)
                current = freeze_selected_search_source(
                    search_port.validated_search_observation(),
                    max_skew_s=route.candidate.max_skew)
                if current != source:
                    raise ValueError("selected source changed")
                self._entry = (broker, ticket, copy.deepcopy(source),
                               copy.deepcopy(prepared), receipt, search_port, route)
                return copy.deepcopy(prepared)
        except BaseException as error:
            with self._lock:
                self._entry = None
            try:
                broker.stop_attempt("VISIBLE_APPROACH_SOURCE_FAILED")
            except BaseException as stop_error:
                raise RuntimeError("VISIBLE_APPROACH_SOURCE_STOP_UNCONFIRMED") from stop_error
            raise ValueError("TRUSTED_VISIBLE_APPROACH_SOURCE_INVALID") from error

    def __call__(self, ticket):
        """Supply only the registered same-ticket source to broker consume."""
        broker = None
        try:
            with self._lock:
                if self._entry is None:
                    raise ValueError("unregistered")
                broker, original, source, prepared, receipt, search_port, route = self._entry
                if broker._prefix_source_port is not self or ticket != original:
                    raise ValueError("ticket")
                self._scope(broker, ticket, source)
                observed = search_port.validated_search_observation()
                if (freeze_selected_search_source(
                        observed, max_skew_s=route.candidate.max_skew) != source
                        or observed.native_controller_ingress_proof.get(
                            "native_ingress_window_sha256") !=
                           prepared["native_ingress_window_sha256"]
                        or native_ingress_digest(observed.native_controller_ingress_proof[
                            "native_snapshots"]) != prepared["native_ingress_window_sha256"]
                        or receipt.owner_ticket != ticket):
                    raise ValueError("selected source changed")
                return copy.deepcopy(source)
        except (AttributeError, KeyError, TypeError, ValueError,
                PermissionError, RuntimeError) as error:
            if broker is not None:
                try:
                    broker.stop_attempt("VISIBLE_APPROACH_SOURCE_CHANGED")
                except BaseException as stop_error:
                    raise RuntimeError("VISIBLE_APPROACH_SOURCE_STOP_UNCONFIRMED") from stop_error
            raise PermissionError("VISIBLE_APPROACH_SOURCE_UNAVAILABLE") from error
