"""Sequential ACT cases reuse their already-admitted private shard instance."""

import math

from so101_demo.parallel_batch.contracts.common import WorkerState
from so101_demo.parallel_batch.worker import ParallelWorker


class ContainerCollectionWorker(ParallelWorker):
    def _recover(self,lease,deadline,*,physical_action_proven_absent):
        self._stop_watchdog()
        if (self._workload is None or self._workload.cleanup_unconfirmed
                or type(deadline) not in (int,float) or not math.isfinite(deadline)
                or self._now()>=deadline):
            self._quarantined=True
            return False
        stopped=False
        receipt=False
        try:
            stopped=self._call_before(lambda:self._runtime.prepare_next_case(lease,
                deadline_monotonic_s=deadline,physical_action_proven_absent=physical_action_proven_absent),
                deadline,'COLLECTION_CASE_CLEANUP_DEADLINE') is True
            location=self._call_before(lambda:self._results.write_recovery_receipt(lease,
                succeeded=stopped,generation=lease.worker_generation,deadline_monotonic_s=deadline,clock=self._clock),
                deadline,'COLLECTION_CASE_RECEIPT_DEADLINE')
            receipt=self._call_before(lambda:self._results.verify_recovery_receipt(location,lease,
                succeeded=stopped,generation=lease.worker_generation,deadline_monotonic_s=deadline,clock=self._clock),
                deadline,'COLLECTION_CASE_RECEIPT_READBACK_DEADLINE') is True
            succeeded=stopped and receipt
            ack=self._call_before(lambda:self._coordinator.record_recovery(self._worker_id,
                generation=lease.worker_generation,succeeded=succeeded,fenced=stopped,
                owned_processes_stopped=stopped,controllers_stopped=stopped,readmitted=succeeded,
                recovery_deadline_monotonic_s=deadline),deadline,'COLLECTION_CASE_RECOVERY_ACK_DEADLINE')
            if (not succeeded or ack.state is not WorkerState.AVAILABLE
                    or ack.generation!=lease.worker_generation):
                self._quarantined=True
                return False
            # Shared services and the local Teacher adapter remain borrowed.
            # The next reset supplies a new lease/reset epoch in the same
            # registered instance; only a new wave creates a new generation.
            self._ready_after_recovery=True
            return True
        except Exception:
            self._quarantined=True
            return False
