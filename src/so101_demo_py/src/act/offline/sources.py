"""The Recorder's own sources, served from a bag replay (P2).

`OfflineRosSources` is `RosRecorderSources` unchanged except for the four things a replay cannot do like a live node:

* messages arrive through `ReplayNode.deliver_due` (the receiver's job live), at their recorded receipt instants;
* the planning-scene reads the live Recorder made over `/get_planning_scene` are the record-only process's reads, replayed from
  `/so101/raw/planning_scene_reads` at the instant each finished (the shape is the Teacher's `scene_operation` payload);
* the alignment verification runs inline (a thread would only add wall-clock races to a deterministic replay);
* there is no scene poller thread: the reads are visible when their message has been delivered.

Every rule, gate and check of `RosRecorderSources` and `RecorderEngine` is the live one.
"""

from __future__ import annotations

import json
import time

from ...ros.episode_recorder_sources import RosRecorderSources
from .raw_recorder import SCENE_READS_TOPIC
from .replay import InlineExecutor, ReplayNode, ReplayReceiver


class OfflineRosSources(RosRecorderSources):
    #: virtual time one waiting pass of the data side costs (about one loop pass of the live Recorder)
    PROGRESS_STEP_S = 0.002

    def __init__(self, node: ReplayNode, episode, options, *, faults, policy=None, final_normal_stop_seq=None, **kwargs) -> None:
        super().__init__(node, episode, options, faults=faults, policy=policy, receiver_factory=ReplayReceiver, **kwargs)
        #: the Teacher publishes a `normal_stop` for every confirmed stop; the bag shows which one is the last (CP-3440)
        self._final_normal_stop_seq = final_normal_stop_seq
        self._final_boundary_done = False
        self._scene_reads_pending: list = []
        self._scene_reads_seen = 0

    def prepare(self, engine) -> None:
        from std_msgs.msg import String

        super().prepare(engine)
        if self._executor is not None:
            self._executor.shutdown(wait=False)
        self._executor = InlineExecutor()
        # The data side waits in loops that call `progress` (the first world after the stop, the camera tail). Live, each pass costs
        # real time and the loop ends at its deadline; on a virtual clock a pass that costs nothing would never reach the deadline.
        self.host._progress_callable = lambda: (self.node.clock.advance(self.PROGRESS_STEP_S), self.pump(engine))[1]
        self._scene_subscription = self.node.create_subscription(String, SCENE_READS_TOPIC, self._on_scene_read, 1000)

    # -- planning scene reads ---------------------------------------------------------------------------------------

    def _on_scene_read(self, message) -> None:
        self._scene_reads_pending.append(message.data)

    def _start_scene_poller(self):
        return None   # the reads come from the bag; nothing polls

    def _refresh_scene(self) -> None:
        """Make the reads that have been delivered visible to the row audit, in recorded order."""
        from ...act.scene_operation import scene_operation_record

        pending, self._scene_reads_pending = self._scene_reads_pending, []
        for text in pending:
            line = json.loads(text)
            record, _request, _response = scene_operation_record(line["payload"])
            with self._planning_lock:
                self._planning_calls.append(record)
            self._scene_reads_seen += 1
            self._scene_queries["count"] += 1

    def on_teacher_event(self, engine, event) -> None:
        if (event["type"] == "normal_stop" and self._final_normal_stop_seq is not None
                and event["seq"] != self._final_normal_stop_seq and self.host is not None):
            self.host._data_skip_normal_stop_boundary = True    # audited, not the boundary
        super().on_teacher_event(engine, event)
        if (event["type"] == "normal_stop" and event["seq"] == self._final_normal_stop_seq and not self._final_boundary_done
                and self.host is not None and self.host._retained_normal_stop() is not None):
            # The final boundary is the first world record after the stop, at most 100 ms of simulation time later. The Teacher
            # takes its end observation and publishes `terminal` 0.5 s after its final stop (pilot bag), so searching for the
            # boundary only after `terminal` (the tail) can never meet that bound. The search starts when the stop is known.
            self._final_boundary_done = True
            end_lag = getattr(self.binding.physics_adapter, "end_lag_check", None)
            if end_lag is not None:
                end_lag()
            self.host._finish_native_collection(time.monotonic() + engine.policy["finish_budget_s"])

    def tail_ready(self, engine) -> bool:
        if self._final_boundary_done and not self._finish_started:
            # the event summary and the reference continuity are sealed once, after the last Teacher event (the terminal)
            self._finish_started = True
            self._seal_event_and_reference_facts(engine)
        return super().tail_ready(engine)

    # -- one pass ---------------------------------------------------------------------------------------------------

    def pump(self, engine) -> None:
        self.node.deliver_due()
        self._refresh_scene()
        super().pump(engine)
