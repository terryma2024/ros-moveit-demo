"""The data side of one recording: Teacher event retention, original boundaries and world sources (Phase A4c).

These functions used to live on `RosDynamicMujocoExecution`, in the Teacher's own process. They are moved here unchanged
(except where noted) so that the independent Recorder process owns them and no longer imports the Teacher's execution
module. The class holds no control object: it is given the episode, the source binding, the world observer and three
callables (`progress`, `normal_stop_proof`, `invalid_latched`) by whoever runs the Recorder loop, and it never creates a
client, a service call or a command connection.
"""

from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path


def _mark_phase(name):
    """Observation only: the Recorder has no phase timer, so this is a named no-op kept where the moved code marks."""


class RecorderDataSide:
    def __init__(self, *, node, session_id, reset_epoch, episode, binding, world_observer, execution_root, progress,
                 normal_stop_proof, invalid_latched, drain_collection, native_source_wait_s=0.1) -> None:
        self._node, self._session_id, self._expected_reset_epoch = node, session_id, reset_epoch
        self.episode_recorder, self._scene_source_binding, self.observer = episode, binding, world_observer
        self._execution_snapshot_root = execution_root
        self._world_record_cursor = None
        self._progress_callable = progress
        self._normal_stop_proof_callable = normal_stop_proof
        self._invalid_latched_callable = invalid_latched
        self._drain_collection_callable = drain_collection
        #: how long a world source may wait for its raw chunk step before the boundary search gives up (CP-3410: the Recorder's
        #: receiver-lag policy; it was a fixed 100 ms, the chunk delivery-age rule seen from the boundary code)
        self._native_source_wait_ns = round(native_source_wait_s * 1e9)

    def _progress(self):
        return self._progress_callable()

    def _normal_stop_proof(self):
        return self._normal_stop_proof_callable()

    def _data_invalid_latched(self):
        return self._invalid_latched_callable()

    def _drain_collection(self):
        return self._drain_collection_callable()

    def _consume_teacher_event(self, episode, event) -> None:
        """Validate and retain one `SO101_TEACHER_EVENT` event. Any problem is a data problem and raises only to the
        data caller. Scene operations never arrive here (the sources route them to the scene tracker).

        `seq` contiguity across all events is the engine's `EventStreamMonitor` and the sealed summary; here the retained
        events only have to be strictly ordered, because scene operations take numbers this side never sees.
        """
        from ..act.teacher_collection import (
            SCHEMA, first_command_clock, normal_stop_boundary_from_event,
            validate_teacher_event)

        if event.get("schema") != SCHEMA:
            raise RuntimeError(f"TEACHER_EVENT_SCHEMA_UNKNOWN: {event.get('schema')}")
        last = getattr(self, "_data_event_last_seq", 0)
        if type(event.get("seq")) is not int or event["seq"] <= last:
            raise RuntimeError(f"TEACHER_EVENT_SEQUENCE_REPEATED: after {last} got {event.get('seq')}")
        validate_teacher_event(event, identity=episode.identity)
        self._data_event_last_seq = event["seq"]
        episode.capture.audit.append_teacher_event(copy.deepcopy(event))
        kind = event["type"]
        if kind == "reset_complete":
            self._data_check_reset_event(event)
        elif kind == "phase_begin":
            clock = first_command_clock(event)
            if clock is not None:
                self._data_retain_first_command(episode, clock)
        elif kind == "normal_stop":
            self._data_retain_normal_stop(episode, normal_stop_boundary_from_event(event))
        elif kind == "terminal":
            self._data_terminal = copy.deepcopy(event["payload"])

    def retain_epoch_boundary(self, episode, boundary) -> None:
        """Retain the verified reset (the Recorder's own first evidence of the epoch) once, at the capture start."""
        from ..act.collection_boundaries import validate_verified_reset
        from ..act.scene_association import canonical

        original = validate_verified_reset(boundary, identity=episode.identity)
        if getattr(self, "_data_verified_reset", None) is not None:
            raise PermissionError("EPISODE_RESET_BOUNDARY_REPEATED")
        episode.capture.audit.append_collection_boundary("verified_reset", original)
        self._data_verified_reset = canonical(original)

    def _data_check_reset_event(self, event) -> None:
        """The Teacher's `reset_complete` must be consistent with the retained boundary (it can only come after it)."""
        from ..act.teacher_collection import validate_reset_complete_matches, validate_reset_complete_payload

        validate_reset_complete_payload(event)          # a malformed payload is the Teacher's defect: ValueError as ever
        if getattr(self, "_data_verified_reset", None) is None:
            raise PermissionError("TEACHER_RESET_BEFORE_RECORDER_EVIDENCE")
        try:
            validate_reset_complete_matches(event, json.loads(self._data_verified_reset))
        except ValueError as error:
            raise PermissionError("TEACHER_RESET_EVENT_INCONSISTENT: " + str(error)) from error

    def _data_retain_first_command(self, episode, clock) -> None:
        """The first goal-sending `phase_begin` starts the capture deadline and fixes the first-command clock."""
        if getattr(self, "_data_first_dispatch_begin_ns", None) is not None:
            return
        self._data_first_dispatch_begin_ns = clock["begin_monotonic_ns"]
        self._data_first_command_clock = copy.deepcopy(clock)
        if episode.capture._first_command_s is None:
            episode.capture.on_event(dict(kind="first_command", sim_time_s=clock["sim_time_ns"] / 1e9,
                                          source_clock=clock))

    def _retained_normal_stop(self):
        """The V2 normal-stop boundary the Teacher's `normal_stop` event carried, or None. No request is made."""
        return getattr(self, "_data_normal_stop", None)

    def _data_retain_normal_stop(self, episode, boundary) -> None:
        from ..act.native_endpoints import validate_normal_stop_boundary

        if getattr(self, "_data_skip_normal_stop_boundary", False):
            # the offline processor knows from the whole bag that this stop is not the Teacher's final one (CP-3440): the event
            # is audited like every other, it is not the episode boundary
            self._data_skip_normal_stop_boundary = False
            return
        if getattr(self, "_data_normal_stop", None) is not None:
            raise RuntimeError("TEACHER_NORMAL_STOP_REPEATED")
        validate_normal_stop_boundary(boundary, identity=episode.identity)
        self._data_normal_stop = copy.deepcopy(boundary)
        # The stop is the end of the motion the moment it is known: rows after it must not be labelled. (Applied at the tail only,
        # the capture kept minting rows through the Teacher's end observation, 0.5 s on the pilot bag, and then revoked them.)
        if (getattr(self, "_collection_initial_capture", None) is not None
                and getattr(self, "_data_first_command_clock", None) is not None):
            self._apply_normal_stop(episode)

    def _apply_normal_stop(self, episode) -> None:
        """Fix the confirmed normal-stop boundary in the audit and the capture, once."""
        from ..act.episode_assembly import PointEpisode

        stop = self._retained_normal_stop()
        first_command = getattr(self, '_data_first_command_clock', None)
        if (type(episode) is not PointEpisode or stop is None or first_command is None
                or episode.capture.audit.identity != episode.identity
                or getattr(self, '_collection_initial_capture', None) is None
                or getattr(self, '_collection_normal_end_clock', None) is not None):
            raise PermissionError('DYNAMIC_NORMAL_END_BINDING_INVALID')
        stop_clock = stop['source_clock']
        if (first_command['end_monotonic_ns'] > stop_clock['begin_monotonic_ns']
                or first_command['sim_time_ns'] > stop_clock['sim_time_ns']):
            raise ValueError('DYNAMIC_NORMAL_END_SEQUENCE_ORDER_INVALID')
        episode.capture.audit.append_collection_boundary('normal_stop', stop)
        episode.capture.on_normal_motion_end(stop_clock)
        self._collection_normal_end_clock = copy.deepcopy(stop_clock)

    def _capture_native_initial_step(self):
        """One non-waiting attempt at the original FIRST after the capture start.

        Returns the retained boundary, or None while the retained raw window does not yet cover a world source.
        A refusal raises to the data caller only (INVALID); the Teacher never waits for this.
        """
        from ..act.episode_assembly import PointEpisode
        from ..act.collection_boundaries import validate_verified_reset
        from ..act.native_endpoints import first_world_after_capture_start, validate_source_clock
        episode = getattr(self, 'episode_recorder', None)
        if (type(episode) is not PointEpisode or not episode.capture.started
                or episode.capture.audit.identity != episode.identity
                or getattr(self, '_data_verified_reset', None) is None):
            raise PermissionError('DYNAMIC_INITIAL_BOUNDARY_BINDING_INVALID')
        retained = getattr(self, '_collection_initial_capture', None)
        if retained is not None:
            return copy.deepcopy(retained)
        start = getattr(self, '_collection_capture_start_clock', None)
        if start is None:
            return None
        reset = validate_verified_reset(json.loads(self._data_verified_reset), identity=episode.identity)
        iterations = getattr(self, '_data_initial_iterations', 0) + 1
        self._data_initial_iterations = iterations
        loop_begin = getattr(self, '_data_initial_begin_ns', None)
        if loop_begin is None:
            loop_begin = self._data_initial_begin_ns = time.monotonic_ns()
            _mark_phase('initial.enter')
        now = time.monotonic_ns()
        if now / 1e9 >= episode.identity['lease']['lease_deadline_monotonic_s']:
            raise PermissionError('DYNAMIC_INITIAL_BOUNDARY_LEASE_EXPIRED')
        sources = self.original_collection_worlds()
        sources, raw = self._windowed_native_sources(sources)
        steps = {sample['physics_step'] for sample in raw}
        missing = [source for source in sources if source['physics']['simulation_step'] not in steps]
        if any(raw and source['physics']['simulation_step'] <= max(steps) for source in missing):
            self._endpoint_source_facts('initial', sources, raw, missing)
            raise ValueError('ENDPOINT_NATIVE_SOURCE_INVALID')
        # CP-3489 (T08, T13, T14 of the first v2 round): a world source newer than the newest retained raw chunk has no native step
        # yet - its chunk is published 100 ms later. The selection needs raw steps only for the sources it examines, so it runs on
        # the covered prefix; waiting for the newer sources to be covered too made the capture land a whole chunk late, more than
        # 100 ms after the first eligible source whenever a world source fell on the first step of the next chunk.
        covered = [source for source in sources if source['physics']['simulation_step'] in steps]
        if not covered:
            if self._native_sources_expired('initial', sources, raw, missing, now):
                raise RuntimeError('DYNAMIC_INITIAL_NATIVE_SOURCE_EXPIRED')
            return None
        waiting_for = missing
        sources = covered
        if not getattr(self, '_data_initial_selectable_marked', False):
            _mark_phase('initial.first_selectable')
            self._data_initial_selectable_marked = True
        _mark_phase('initial.capture')
        begin = time.monotonic_ns()
        stamp = self._node.get_clock().now().nanoseconds
        provisional = dict(sim_time_ns=stamp, begin_monotonic_ns=begin, end_monotonic_ns=begin)
        try:
            selected = first_world_after_capture_start(sources, identity=episode.identity,
                reset_clock=reset['source_clock'], capture_start_clock=start,
                capture_clock=provisional, raw_steps=raw)
        except ValueError as error:
            if str(error) == 'ENDPOINT_INITIAL_CAPTURE_INVALID':
                floor = max(reset['source_clock']['sim_time_ns'], start['sim_time_ns'])
                self._capture_facts('initial', sources, raw, provisional,
                    lambda source, sample: (sample is not None
                        and round(source['physics']['simulation_time_s'] * 1e9) >= floor
                        and sample['clock_interval_begin_monotonic_ns'] >= start['end_monotonic_ns']),
                    start['sim_time_ns'], start['end_monotonic_ns'], iterations, loop_begin)
                raise
            if str(error) != 'ENDPOINT_INITIAL_SOURCE_UNAVAILABLE':
                raise
            if waiting_for and self._native_sources_expired('initial', sources, raw, waiting_for, now):
                raise RuntimeError('DYNAMIC_INITIAL_NATIVE_SOURCE_EXPIRED')
            return None
        clock = validate_source_clock(dict(provisional, end_monotonic_ns=time.monotonic_ns()))
        first_dispatch = getattr(self, '_data_first_dispatch_begin_ns', None)
        if first_dispatch is not None and clock['end_monotonic_ns'] > first_dispatch:
            raise RuntimeError('DYNAMIC_INITIAL_BOUNDARY_AFTER_FIRST_COMMAND')
        document = dict(source_clock=clock, world_source=selected)
        episode.capture.audit.append_collection_boundary('initial_capture', document)
        self._collection_initial_capture = copy.deepcopy(document)
        return document

    def _finish_native_collection(self, deadline_s):
        """Close the data window: stop proof, original final FIRST and camera tail, before `deadline_s` (monotonic)."""
        from ..act.episode_assembly import PointEpisode
        from ..act.native_endpoints import first_world_after_stop, validate_source_clock

        def within_window(code):
            if self._data_invalid_latched():
                raise RuntimeError("ACT_DATA_ALREADY_INVALID")
            if time.monotonic() > deadline_s:
                raise RuntimeError(code)

        episode = getattr(self, 'episode_recorder', None)
        stop = self._retained_normal_stop()
        if getattr(self, '_collection_normal_end_clock', None) is None:
            self._apply_normal_stop(episode)        # not yet applied on arrival (no capture or first command at that moment)
        elif (type(episode) is not PointEpisode or stop is None):
            raise PermissionError('DYNAMIC_NORMAL_END_BINDING_INVALID')
        stop_clock = stop['source_clock']
        anchor = stop['epoch']['publisher_sequence']
        loop_begin = time.monotonic_ns()
        iterations = 0
        while True:
            iterations += 1
            within_window('DYNAMIC_FINAL_BOUNDARY_WINDOW_EXPIRED')
            now = time.monotonic_ns()
            if now / 1e9 >= episode.identity['lease']['lease_deadline_monotonic_s']:
                raise PermissionError('DYNAMIC_FINAL_BOUNDARY_LEASE_EXPIRED')
            sources = [source for source in self.original_collection_worlds()
                       if source['physics']['publisher_sequence'] >= anchor]
            if sources and sources[0]['physics']['publisher_sequence'] > anchor:
                raise ValueError('ENDPOINT_STOP_PREDECESSOR_REQUIRED')
            sources, raw = self._windowed_native_sources(sources)
            steps = {sample['physics_step'] for sample in raw}
            missing = [source for source in sources if source['physics']['simulation_step'] not in steps]
            if any(raw and source['physics']['simulation_step'] <= max(steps) for source in missing):
                self._endpoint_source_facts('final', sources, raw, missing)
                raise ValueError('ENDPOINT_NATIVE_SOURCE_INVALID')
            # Only the world records before the first one that still waits for its physics chunk can be the final boundary: a record
            # after it is not needed to select it, and waiting for the next chunk (up to 100 ms of simulation, one chunk) made the
            # capture clock lag the selected record by more than the 100 ms the endpoint allows (CP-3394, L2 e6be258c: 110 ms).
            ready = sources if not missing else sources[:next(i for i, source in enumerate(sources) if source is missing[0])]
            if not ready:
                if self._native_sources_expired('final', sources, raw, missing, now):
                    raise RuntimeError('DYNAMIC_FINAL_NATIVE_SOURCE_EXPIRED')
                self._progress()
                continue
            begin = time.monotonic_ns()
            stamp = self._node.get_clock().now().nanoseconds
            provisional = dict(sim_time_ns=stamp, begin_monotonic_ns=begin, end_monotonic_ns=begin)
            try:
                selected = first_world_after_stop(ready, stop, identity=episode.identity,
                                                  capture_clock=provisional, raw_steps=raw)
            except ValueError as error:
                if str(error) == 'ENDPOINT_CAPTURE_CLOCK_INVALID':
                    self._capture_facts('final', sources, raw, provisional,
                        lambda source, sample: (sample is not None
                            and source['physics']['publisher_sequence'] > anchor
                            and round(source['physics']['simulation_time_s'] * 1e9) >= stop_clock['sim_time_ns']),
                        stop_clock['sim_time_ns'], stop_clock['end_monotonic_ns'], iterations, loop_begin)
                    raise
                if str(error) != 'ENDPOINT_FINAL_SOURCE_UNAVAILABLE':
                    raise
                if missing and self._native_sources_expired('final', sources, raw, missing, now):
                    raise RuntimeError('DYNAMIC_FINAL_NATIVE_SOURCE_EXPIRED')
                self._progress()
                continue
            clock = validate_source_clock(dict(provisional, end_monotonic_ns=time.monotonic_ns()))
            value = dict(source_clock=clock, world_source=selected)
            episode.capture.audit.append_collection_boundary('final_capture', value)
            self._collection_final_capture = copy.deepcopy(value)
            break
        capture = episode.capture
        while True:
            within_window('DYNAMIC_CAMERA_TAIL_WINDOW_EXPIRED')
            if time.monotonic_ns() / 1e9 >= episode.identity['lease']['lease_deadline_monotonic_s']:
                raise PermissionError('DYNAMIC_CAMERA_TAIL_LEASE_EXPIRED')
            with capture.ingress_lock:
                frames = {camera: values[-1] for camera, values in capture._frames.items() if values}
            if any((frame.session_id, frame.reset_epoch) != (episode.identity['session_id'],
                                                             episode.identity['reset_epoch'])
                   for frame in frames.values()):
                raise ValueError('DYNAMIC_CAMERA_TAIL_SCOPE_INVALID')
            if set(frames) == {'head', 'wrist'} and all(
                    round(frame.stamp_s * 1e9) >= stop_clock['sim_time_ns'] for frame in frames.values()):
                break
            self._progress()
        self._drain_collection()
        return copy.deepcopy(stop_clock)

    def _windowed_native_sources(self, sources):
        """Keep only world sources inside the retained raw window; return (sources, raw steps)."""
        adapter=self._scene_source_binding.physics_adapter
        window=adapter.retained_step_range()
        if window is None:
            return [],[]
        sources=[source for source in sources if source['physics']['simulation_step']>=window[0]]
        floor=sources[0]['physics']['simulation_step'] if sources else window[0]
        return sources,adapter.original_durable_steps(min_physics_step=floor)

    def _native_sources_expired(self,site,sources,raw,missing,now):
        """True when a missing source's raw step was never received and its source is older than the wait (100 ms by default; the
        Recorder passes its receiver-lag policy, CP-3410).

        A step at or below the adapter's received maximum is covered by a received chunk that is only
        waiting for the next drain, so drain latency is not delivery latency. Prints one facts line
        (observation only, never raises) before a True result.
        """
        if not missing:
            return False
        received_max=self._scene_source_binding.physics_adapter.received_max_step()
        expired=[source for source in missing
            if (received_max is None or source['physics']['simulation_step']>received_max)
            and now-max(source['received_monotonic_ns'],source['scene_received_monotonic_ns'])>getattr(self,'_native_source_wait_ns',100_000_000)]
        if not expired:
            return False
        try:
            adapter=self._scene_source_binding.physics_adapter
            durable=[sample['physics_step'] for sample in raw]
            try:pending=adapter.history_summary()['pending']
            except BaseException:pending=None
            doc=dict(site=site,now_ns=now,received_max_step=received_max,
                durable_max_step=max(durable,default=None),
                expired_steps_first10=[source['physics']['simulation_step'] for source in expired[:10]],
                expired_ages_ms_first10=[(now-max(source['received_monotonic_ns'],
                    source['scene_received_monotonic_ns']))/1e6 for source in expired[:10]],
                pending_count=pending)
            line='ENDPOINT_NATIVE_SOURCE_EXPIRED_FACTS '+json.dumps(doc,sort_keys=True,separators=(',',':'),default=str)
            print(line.encode()[:4000].decode(errors='ignore'),file=sys.stderr,flush=True)
        except BaseException:
            pass
        return True

    @staticmethod
    def _endpoint_source_facts(site,sources,raw,missing):
        """Observation only: one facts line before an ENDPOINT_NATIVE_SOURCE_INVALID raise; never raises."""
        try:
            source_steps=[source['physics']['simulation_step'] for source in sources]
            raw_steps=[sample['physics_step'] for sample in raw]
            fields=(('site',site),('sources_count',len(source_steps)),
                ('source_step_min',min(source_steps,default=None)),('source_step_max',max(source_steps,default=None)),
                ('raw_count',len(raw_steps)),('raw_step_min',min(raw_steps,default=None)),
                ('raw_step_max',max(raw_steps,default=None)),
                ('missing_steps_first10',[source['physics']['simulation_step'] for source in missing[:10]]))
            line='ENDPOINT_NATIVE_SOURCE_FACTS '+' '.join(f'{name}={value}' for name,value in fields)
            print(line.encode()[:4000].decode(errors='ignore'),file=sys.stderr,flush=True)
        except BaseException:
            pass

    def _capture_facts(self,site,sources,raw,capture,pick,start_sim_ns,start_end_ns,iterations,loop_begin_ns):
        """Observation only: one ENDPOINT_INITIAL_CAPTURE_FACTS line before a capture-freshness refusal; never raises."""
        try:
            native={sample['physics_step']:sample for sample in raw}
            selected=next((source for source in sources
                if pick(source,native.get(source['physics']['simulation_step']))),None)
            adapter=self._scene_source_binding.physics_adapter
            def guarded(read):
                try:return read()
                except BaseException:return None
            stamp=None if selected is None else round(selected['physics']['simulation_time_s']*1e9)
            doc=dict(site=site,capture_sim_ns=capture['sim_time_ns'],capture_begin_ns=capture['begin_monotonic_ns'],
                selected_step=None if selected is None else selected['physics']['simulation_step'],
                selected_stamp_ns=stamp,
                delta_sim_ms=None if stamp is None else (capture['sim_time_ns']-stamp)/1e6,
                selected_received_ns=None if selected is None else selected['received_monotonic_ns'],
                selected_scene_received_ns=None if selected is None else selected['scene_received_monotonic_ns'],
                capture_start_sim_ns=start_sim_ns,capture_start_end_ns=start_end_ns,
                raw_received_max_step=guarded(adapter.received_max_step),
                raw_durable_max_step=max(native,default=None),
                pending_count=guarded(lambda:adapter.history_summary()['pending']),
                loop_iterations=iterations,
                loop_elapsed_ms=(time.monotonic_ns()-loop_begin_ns)/1e6)
            line='ENDPOINT_INITIAL_CAPTURE_FACTS '+json.dumps(doc,sort_keys=True,separators=(',',':'),default=str)
            print(line.encode()[:4000].decode(errors='ignore'),file=sys.stderr,flush=True)
        except BaseException:
            pass

    def original_collection_worlds(self):
        """Read only copies of originals already retained by the existing audit writer."""
        return copy.deepcopy(list(getattr(self,'_collection_world_history',())))

    def _drain_world_sources(self):
        episode = getattr(self, "episode_recorder", None)
        cursor = getattr(self, "_world_record_cursor", None)
        if episode is None or cursor is None:
            return 0
        if getattr(self, "_collection_final_capture", None) is not None:
            return 0   # the episode's world sources end with its final boundary (a later record has no raw sample yet at the seal)
        from ..act.native_endpoints import world_source_record
        binding = self._scene_source_binding
        records = self.observer.original_records_after(cursor)
        if not records:
            return 0
        # Records first: a scene that arrives later can only add matches. Copy only frames the pending records can match.
        scenes = binding.observer.original_frames_with_receipts(
            min_simulation_step=records[0].evidence.simulation_step)
        written = 0
        for received in records:
            world = received.evidence
            if (world.simulation_session_id, world.reset_epoch) != (self._session_id, self._expected_reset_epoch):
                raise RuntimeError("DYNAMIC_WORLD_SOURCE_SCOPE_INVALID")
            waiting = getattr(self, "_world_scene_wait", None)
            matched = [(frame, receipt) for frame, receipt in scenes if
                (frame["simulation_session_id"], frame["reset_epoch"], frame["simulation_step"])
                == (world.simulation_session_id, world.reset_epoch, world.simulation_step)]
            if len(matched) > 1:
                raise RuntimeError("DYNAMIC_WORLD_SOURCE_AMBIGUOUS")
            if not matched:
                # The frame is looked for FIRST. Only a frame that is still absent after the 100 ms is missing: a pass
                # that merely came late (a stall of this loop) must not fail a join the receiver already satisfied.
                if waiting is None:
                    self._world_scene_wait = (world.publisher_sequence, time.monotonic())
                elif waiting[0] != world.publisher_sequence or time.monotonic() - waiting[1] > .1:
                    self._scene_missing_facts(received, scenes, waiting)
                    raise RuntimeError("DYNAMIC_WORLD_SOURCE_SCENE_MISSING")
                break
            if matched[0][1] - received.received_monotonic_s > .1:
                # The 100 ms delivery rule on the receipts themselves (stamped when each message arrived), not on this
                # loop's cadence: a frame that really came more than 100 ms after its world record is missing.
                raise RuntimeError("DYNAMIC_WORLD_SOURCE_SCENE_MISSING")
            record = world_source_record(received, matched[0], execution_root=self._execution_snapshot_root)
            episode.capture.audit.append_world_source(record)
            if getattr(self,'_collection_world_history',None) is None:
                from collections import deque
                self._collection_world_history=deque(maxlen=512)
            self._collection_world_history.append(copy.deepcopy(record))
            self._world_record_cursor = world.publisher_sequence
            self._world_scene_wait = None
            written += 1
        return written

    def _scene_missing_facts(self, received, scenes, waiting) -> None:
        """Observation only: what the scene ring held when a world record's frame was missing; never raises."""
        try:
            binding = self._scene_source_binding
            steps = [frame["simulation_step"] for frame, _ in scenes]
            document = {
                "kind": "WORLD_SCENE_JOIN_FAILURE", "monotonic_ns": time.monotonic_ns(),
                "world": {"publisher_sequence": received.evidence.publisher_sequence,
                          "simulation_step": received.evidence.simulation_step,
                          "received_monotonic_s": received.received_monotonic_s},
                "waited_s": time.monotonic() - waiting[1],
                "scene_ring": {"count": len(scenes), "steps_first_last": [steps[0], steps[-1]] if steps else None,
                               "receipts_first_last_s": [scenes[0][1], scenes[-1][1]] if scenes else None,
                               "observer_hazard": getattr(binding.observer, "hazard", None)},
                "adapter_rejected": getattr(getattr(binding, "adapter", None), "rejected", None)}
            root = Path(self.episode_recorder.capture.audit.root).parent
            temporary = root / "world-scene-failure.json.tmp"
            temporary.write_text(json.dumps(document, sort_keys=True, default=str))
            temporary.replace(root / "world-scene-failure.json")
        except BaseException:
            pass

    def _step_data_initial_boundary(self) -> None:
        """One non-waiting attempt at the initial boundary; INVALID once the first command went out without it.

        Cheap checks first (CP-3423): after the first command the boundary can no longer be honest (its clock would end after
        the command), so the verdict is raised ONCE and the search is never run again; and an attempt is skipped while
        nothing it reads has changed since the last unsuccessful one. The search deep-copies the retained worlds and raw
        steps: it cost 89 ms per pass on average and 503 ms at worst, which starved the loop (L2 5daa904e).
        """
        episode = getattr(self, "episode_recorder", None)
        if episode is None or getattr(self, "_data_initial_settled", False):
            return
        if (getattr(self, "_collection_initial_capture", None) is None
                and getattr(self, "_data_first_dispatch_begin_ns", None) is not None):
            self._data_initial_settled = True
            raise RuntimeError("DYNAMIC_INITIAL_BOUNDARY_AFTER_FIRST_COMMAND")
        if (getattr(self, "_collection_initial_capture", None) is None
                and getattr(episode.capture, "started", False)
                and getattr(self, "_data_verified_reset", None) is not None):
            adapter = getattr(getattr(self, "_scene_source_binding", None), "physics_adapter", None)
            received = getattr(adapter, "received_max_step", None)
            key = (getattr(self, "_world_record_cursor", None), received() if callable(received) else None)
            now = time.monotonic()
            if (key == getattr(self, "_data_initial_last_key", None)
                    and now - getattr(self, "_data_initial_last_at", 0.0) < 0.25):
                return   # nothing it reads changed; the expiry rules are still checked four times a second
            self._data_initial_last_key, self._data_initial_last_at = key, now
            try:
                self._capture_native_initial_step()
            except BaseException:
                self._data_initial_settled = True
                raise
