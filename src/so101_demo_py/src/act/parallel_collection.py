"""Partition a frozen manifest into fixed, ordered waves.

The wave boundary is the unit of recovery: a wave is re-entered whole or not at all, and the manifest
order is preserved so a wave record can be compared against the manifest without re-sorting.
"""

from __future__ import annotations


def partition_waves(scene_ids, *, max_wave_size: int = 20) -> tuple:
    """Split `scene_ids` into consecutive waves of at most `max_wave_size`, preserving order.

    Duplicates are refused rather than partitioned: a scene appearing twice in one campaign would make
    a wave record ambiguous and could collect the same scene under two attempts.
    """

    try:
        ids = tuple(scene_ids)
    except TypeError as error:
        raise ValueError("WAVE_MANIFEST_INVALID") from error
    if type(max_wave_size) is not int or max_wave_size < 1:
        raise ValueError("WAVE_SIZE_INVALID")
    if not ids:
        raise ValueError("WAVE_MANIFEST_EMPTY")
    if any(not isinstance(scene_id, str) or not scene_id for scene_id in ids):
        raise ValueError("WAVE_MANIFEST_INVALID")
    if len(set(ids)) != len(ids):
        raise ValueError("WAVE_SCENE_DUPLICATE")
    return tuple(ids[start:start + max_wave_size] for start in range(0, len(ids), max_wave_size))


def reserve_qualification_scenes(scene_ids: tuple, worker_ids: tuple) -> dict:
    """Freeze two adjacent cases per exact-W8 slot and four ordered surplus cases.

    The owner must consume a slot's two reserved terminal leases before issuing
    it surplus. A lost slot never transfers its reservation to a faster Worker.
    """
    from so101_demo.parallel_batch.contracts.common import _require_id
    try:
        if (type(scene_ids) is not tuple or len(scene_ids) != 20
                or type(worker_ids) is not tuple or worker_ids != tuple(f'w{index:02d}' for index in range(8))
                or len(set(scene_ids)) != 20):
            raise ValueError('wave shape')
        for scene_id in scene_ids:
            _require_id('scene_id',scene_id)
    except (ValueError, TypeError) as error:
        raise ValueError('QUALIFICATION_RESERVATIONS_INVALID') from error
    return dict(reserved_by_worker={worker:scene_ids[index*2:index*2+2]
                for index,worker in enumerate(worker_ids)}, surplus=scene_ids[16:])


def reserve_functional_scenes(scene_ids: tuple, worker_ids: tuple) -> dict:
    """Debug-only reservations for a functional eight-worker wave: adjacent, equal, ordered cases per slot, no surplus.

    Shaped like `reserve_qualification_scenes` (8 or 16 scenes give 1 or 2 cases per slot), so the same dispatch and
    scheduling checks apply. It is not qualification evidence and nothing in the gate plane accepts it.
    """
    from so101_demo.parallel_batch.contracts.common import _require_id
    try:
        if (type(scene_ids) is not tuple or len(scene_ids) not in (8, 16)
                or type(worker_ids) is not tuple or worker_ids != tuple(f'w{index:02d}' for index in range(8))
                or len(set(scene_ids)) != len(scene_ids)):
            raise ValueError('wave shape')
        for scene_id in scene_ids:
            _require_id('scene_id',scene_id)
    except (ValueError, TypeError) as error:
        raise ValueError('FUNCTIONAL_RESERVATIONS_INVALID') from error
    each = len(scene_ids) // 8
    return dict(reserved_by_worker={worker:scene_ids[index*each:(index+1)*each]
                for index,worker in enumerate(worker_ids)}, surplus=())


def wave_assignment_for(scene_ids: tuple, worker_ids: tuple) -> dict:
    """The reservation a planned wave must carry: the gate shape for 20 scenes, the functional shape for 8 or 16."""
    if len(scene_ids) == 20:
        return reserve_qualification_scenes(scene_ids, worker_ids)
    return reserve_functional_scenes(scene_ids, worker_ids)


def plan_campaign_waves(scene_ids, worker_ids, *, plane, max_wave_size: int = 20, first_wave_index: int = 0,
                        recording_round: int = 0) -> list:
    """The wave plans of a campaign. `plane` is 'gate' (W8 qualification), 'functional' (debug), 'spot_check' (one contact-policy
    spot check: one worker, one scene, no reservation) or None (formal).

    Only eight workers on the gate or functional plane carry reservations; every other run claims scenes dynamically.

    A retry round (`recording_round` >= 1) continues the wave numbering from `first_wave_index` and is formal (`plane=None`); its
    plans carry the key `recording_round`. Round-0 plans carry no such key, so they stay byte-identical."""
    if (type(first_wave_index) is not int or first_wave_index < 0 or type(recording_round) is not int or recording_round < 0
            or (recording_round > 0 and plane is not None)):
        raise ValueError('CAMPAIGN_ROUND_INVALID')
    if plane not in ('gate', 'functional', 'spot_check', None):
        raise ValueError('CAMPAIGN_PLANE_INVALID')
    worker_ids = tuple(worker_ids)
    reserve = plane in ('gate', 'functional') and len(worker_ids) == 8
    reserver = reserve_qualification_scenes if plane == 'gate' else reserve_functional_scenes
    plans = [dict(wave_index=first_wave_index + index, scene_ids=list(wave),
                  assignment=reserver(wave, worker_ids) if reserve else None)
             for index, wave in enumerate(partition_waves(scene_ids, max_wave_size=max_wave_size))]
    if recording_round:
        for plan in plans:
            plan['recording_round'] = recording_round
    if plane == 'spot_check':
        # marks the plan so the wave verifier does not owe the two-tasks-per-instance count of a qualification wave
        for plan in plans:
            plan['plane'] = 'spot_check'
    return plans


def write_campaign_index(path, *, waves, qualification: bool) -> str:
    """Atomically publish the campaign index: the wave partition and what it was for."""

    import json
    import os
    from pathlib import Path as _Path

    partition = tuple(tuple(wave) for wave in waves)
    if not partition or any(not wave for wave in partition):
        raise ValueError("CAMPAIGN_INDEX_INVALID")
    if type(qualification) is not bool:
        raise ValueError("CAMPAIGN_INDEX_INVALID")
    target = _Path(path)
    if target.exists() or target.is_symlink():
        raise ValueError("CAMPAIGN_INDEX_EXISTS")
    if not target.parent.is_dir():
        raise ValueError("CAMPAIGN_INDEX_INVALID")
    document = {"schema_version": 1, "kind": "act_collection_campaign_index",
                "qualification": qualification,
                "waves": [{"wave_index": index, "scene_ids": list(wave)}
                          for index, wave in enumerate(partition)],
                "scene_count": sum(len(wave) for wave in partition)}
    temporary = target.with_name(target.name + ".partial")
    with open(temporary, "w") as handle:
        handle.write(json.dumps(document, sort_keys=True, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(target)
    return str(target)


_CONFIG_KEYS = frozenset({"max_wave_size", "qualification"})


class FixedActCollectionCampaign:
    """Runs a frozen manifest as fixed waves, publishing one result per scene.

    The resource claim is held until the last scene reaches a terminal state and is released only then:
    a failure leaves the claim held on purpose, so an early exit cannot hand the stack to the next run
    while this campaign's evidence is still unresolved.
    """

    def __init__(self, manifest: dict, config: dict, context, root, *, collect_port, claim,
                 store=None) -> None:
        from pathlib import Path as _Path

        from so101_demo.adapters.act.parallel_collection_results import ActCollectionResultStore

        if not isinstance(manifest, dict) or not isinstance(manifest.get("scenarios"), list):
            raise ValueError("CAMPAIGN_MANIFEST_INVALID")
        rows = manifest["scenarios"]
        if not rows or any(not isinstance(row, dict) or not isinstance(row.get("scene_id"), str)
                           or not isinstance(row.get("split"), str) for row in rows):
            raise ValueError("CAMPAIGN_MANIFEST_INVALID")
        if not isinstance(config, dict) or set(config) != _CONFIG_KEYS:
            raise ValueError("CAMPAIGN_CONFIG_INVALID")
        self.manifest = manifest
        self.config = config
        self.context = context
        self.root = _Path(root)
        self.store = store if store is not None else ActCollectionResultStore(self.root)
        self.collect_port = collect_port
        self.claim = claim
        self.scene_ids = tuple(row["scene_id"] for row in rows)

    def run(self) -> dict:
        from pathlib import Path as _Path

        waves = partition_waves(self.scene_ids, max_wave_size=self.config["max_wave_size"])
        index_path = write_campaign_index(self.root / "campaign-index.json", waves=waves,
                                         qualification=self.config["qualification"])
        terminal, collected, results = [], [], {}
        for wave_index, wave in enumerate(waves):
            for scene_id in wave:
                if self.store.has_result(scene_id):
                    terminal.append(scene_id)              # already sealed: never collected twice
                    continue
                record = self.collect_port.collect(scene_id, self.context,
                                                  {"wave_index": wave_index})
                if not isinstance(record, dict) or record.get("scene_id") != scene_id:
                    raise ValueError("CAMPAIGN_RESULT_INVALID")
                results[scene_id] = self.store.publish(record)
                collected.append(scene_id)
        # only now, with every scene terminal, may the claim be handed on
        self.claim.release({"campaign_index": index_path, "terminal": terminal + collected})
        return {"campaign_index": index_path, "waves": [list(wave) for wave in waves],
                "already_terminal": terminal, "collected": collected, "results": results,
                "scene_count": len(self.scene_ids),
                "claim_released": True}


def campaign_config_from(collection_config: dict, *, qualification: bool) -> dict:
    """Derive the campaign config from the loaded v3 collection config.

    The wave size and the qualification flag come from the frozen collection config; the posture is
    checked here too, because a campaign that retried business failures or quietly degraded would defeat
    the point of running the collection in the first place.
    """

    if type(qualification) is not bool:
        raise ValueError("COLLECTION_QUALIFICATION_MODE_INVALID")
    if not isinstance(collection_config, dict):
        raise ValueError("COLLECTION_CONFIG_INVALID")
    qualification_block = collection_config.get("qualification")
    recovery_block = collection_config.get("recovery")
    if not isinstance(qualification_block, dict) or not isinstance(recovery_block, dict):
        raise ValueError("COLLECTION_CONFIG_INVALID")
    max_wave_size = qualification_block.get("max_wave_size")
    if type(max_wave_size) is not int or max_wave_size < 1:
        raise ValueError("COLLECTION_CONFIG_INVALID")
    if qualification_block.get("no_auto_degrade") is not True:
        raise ValueError("COLLECTION_NO_AUTO_DEGRADE_REQUIRED")
    if recovery_block.get("business_retry_count") != 0:
        raise ValueError("COLLECTION_BUSINESS_RETRY_FORBIDDEN")
    return {"max_wave_size": max_wave_size, "qualification": qualification}


class ActFixedCollectionWorkload:
    """Execute the one scene leased to this shard from the frozen scene list."""

    kind = "act_fixed_collection"

    def __init__(self, *, scene_ids):
        from so101_demo.parallel_batch.contracts.common import _require_id

        if type(scene_ids) is not tuple or not scene_ids or len(set(scene_ids)) != len(scene_ids):
            raise ValueError("ACT_COLLECTION_SCENES_INVALID")
        try:
            for scene_id in scene_ids:
                _require_id("scene_id", scene_id)
        except (ValueError, TypeError) as error:
            raise ValueError("ACT_COLLECTION_SCENES_INVALID") from error
        self.scene_ids = frozenset(scene_ids)
        self.action_may_have_started = False
        self.cleanup_unconfirmed = False

    def run_authorized(self, lease, *, runtime, broker, boundary, teacher_boundary,
                       stop_before_motion, recorder_stopped, start_event_id,
                       start_event_type, reset_epoch):
        from so101_demo.parallel_batch.act_attempt import ActPerceptionDecision, ActPerceptionTerminal
        from so101_demo.parallel_batch.act_inference import ActLocalizedPose
        from so101_demo.parallel_batch.contracts.common import ExecutionKind
        from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
        from so101_demo.runtime.parallel_ros_ports.observations import AdmittedPose

        if self.cleanup_unconfirmed:
            raise ValueError("ACT_COLLECTION_CLEANUP_UNCONFIRMED")
        self.action_may_have_started = False
        if type(lease) is not LeaseIdentity or lease.point_id not in self.scene_ids:
            raise ValueError("ACT_COLLECTION_SCENE_NOT_RESERVED")
        if (start_event_id != f"attempt-start-{lease.attempt_id}"
                or start_event_type != "ATTEMPT_STARTED"):
            raise ValueError("ACT_COLLECTION_LOCAL_START_MISMATCH")
        snapshot = boundary(lambda current: runtime.inference_snapshot(current))
        chain = boundary(lambda current: broker.request_model(current, ExecutionKind.ATTEMPT,
            snapshot=snapshot, start_event_id=start_event_id, start_event_type=start_event_type,
            reset_epoch=reset_epoch))
        if type(chain) is ActPerceptionTerminal:
            request = chain.request
        elif type(chain) is AdmittedPose and type(chain.localized) is ActLocalizedPose:
            request = chain.localized.request
        else:
            raise ValueError("ACT_COLLECTION_PERCEPTION_RESULT_REQUIRED")
        fields = ("batch_id", "coordinator_epoch", "worker_id", "worker_generation",
                  "point_id", "attempt_id", "lease_generation")
        if (any(getattr(request, field) != getattr(lease, field) for field in fields)
                or request.reset_epoch != reset_epoch):
            raise ValueError("ACT_COLLECTION_TERMINAL_LEASE_MISMATCH")
        if type(chain) is ActPerceptionTerminal:
            _decision, fenced, stopped, confirmed = stop_before_motion(lease)
            decision = ActPerceptionDecision.from_terminal(chain, stop_facts=dict(fenced=fenced,
                motion_stopped=stopped, controllers_stopped=confirmed,
                recorder_stopped=recorder_stopped(lease)))
            self.cleanup_unconfirmed = not all(decision.stop_facts.values())
            return decision
        admitted = boundary(lambda current: runtime.admit_pose(current, chain))
        if admitted is not chain:
            raise ValueError("ACT_COLLECTION_ADMITTED_POSE_CHANGED")
        self.action_may_have_started = True
        return teacher_boundary(lambda current: runtime.execute_expert(current, admitted))
