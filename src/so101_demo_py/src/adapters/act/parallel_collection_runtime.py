"""Task 11A runtime adapter: one scenario collected inside an admitted lease.

This is the only place the campaign's abstract per-scene collection meets the real ports. It refuses to
touch a scenario until the lease reports it is admitted, prepares the scenario exactly once (Task 11's
rule), and runs the collection half that structurally has no reset port of its own.
"""

from __future__ import annotations

from so101_demo.act.collection import collect_authorized_scenario, prepare_scenario

_LEASE_KEYS = ("admitted", "reset_epoch")


class ActFixedCollectionRuntime:
    """Binds `FixedActCollectionCampaign` to a lease and the four scenario ports."""

    def __init__(self, *, lease_port, reset_port, joints_port, phase_port, recorder_port,
                 qc_port, ledger, boundary=None) -> None:
        self.lease_port = lease_port
        self.reset_port = reset_port
        self.joints_port = joints_port
        self.phase_port = phase_port
        self.recorder_port = recorder_port
        self.qc_port = qc_port
        self.ledger = ledger
        self.boundary = boundary

    def _require_lease(self):
        lease = self.lease_port.lease()
        if (not isinstance(lease, dict) or lease.get("admitted") is not True
                or type(lease.get("reset_epoch")) is not int):
            # an unadmitted lease means no scenario work of any kind, not even a reset
            raise ValueError("ACT_COLLECTION_LEASE_UNAVAILABLE")
        return lease

    def collect(self, scene_id, context, wave) -> dict:
        lease = self._require_lease()
        scenario = getattr(context, "scenario", None)
        if not isinstance(scenario, dict) or scenario.get("scene_id") != scene_id:
            raise ValueError("ACT_COLLECTION_SCENARIO_UNAVAILABLE")

        def work(current):
            prepared = prepare_scenario(current, reset_port=self.reset_port,
                                        joints_port=self.joints_port, ledger=self.ledger,
                                        attempt_id=f"{scene_id}:{wave['wave_index']}")
            prepared["lease_reset_epoch"] = lease["reset_epoch"]
            return collect_authorized_scenario(prepared, current, phase_port=self.phase_port,
                                               recorder=self.recorder_port, qc_port=self.qc_port,
                                               ledger=self.ledger)

        if self.boundary is None:
            return work(scenario)
        return self.boundary(work)
