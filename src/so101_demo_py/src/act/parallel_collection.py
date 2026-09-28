"""Task 11A: partition a frozen manifest into fixed, ordered waves.

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


QUALIFICATION_KINDS = frozenset({"W1", "W2", "W8"})
_W8_SCENES = 40


def create_qualification_contract(path, *, payload: dict, kind: str) -> str:
    """Atomically create the qualification contract BEFORE any spawn, or refuse.

    An existing or non-persistable path is a refusal, never an overwrite: a second campaign must not
    inherit or silently replace another run's qualification evidence.
    """

    import json
    import os
    from pathlib import Path as _Path

    if kind not in QUALIFICATION_KINDS:
        raise ValueError("QUALIFICATION_KIND_INVALID")
    if not isinstance(payload, dict) or not payload:
        raise ValueError("QUALIFICATION_PAYLOAD_INVALID")
    target = _Path(path)
    if target.exists() or target.is_symlink():
        raise ValueError("QUALIFICATION_CONTRACT_EXISTS")
    parent = target.parent
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        raise ValueError("QUALIFICATION_CONTRACT_NOT_PERSISTABLE")
    document = {"schema_version": 1, "kind": kind, **payload}
    temporary = target.with_name(target.name + ".partial")
    with open(temporary, "w") as handle:
        handle.write(json.dumps(document, sort_keys=True, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(target)
    return str(target)


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


def require_collection_mode(*, manifest_kind: str, qualification_mode: bool, contract=None) -> None:
    """Qualification runs accept W1/W2/W8; a formal run must be exact W8 under a live 40-scene gate."""

    if type(qualification_mode) is not bool:
        raise ValueError("COLLECTION_QUALIFICATION_MODE_INVALID")
    if qualification_mode:
        if manifest_kind not in QUALIFICATION_KINDS:
            raise ValueError("QUALIFICATION_MANIFEST_KIND_INVALID")
        return
    if manifest_kind != "W8":
        raise ValueError("FORMAL_MANIFEST_NOT_EXACT_W8")
    if not isinstance(contract, dict) or contract.get("revoked") is not False:
        raise ValueError("FORMAL_QUALIFICATION_CONTRACT_MISSING_OR_REVOKED")
    if contract.get("scenes") != _W8_SCENES:
        raise ValueError("FORMAL_QUALIFICATION_SCENE_COUNT_INVALID")


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
        qualification = config["qualification"]
        require_collection_mode(manifest_kind=manifest.get("kind", "W8"),
                                qualification_mode=qualification,
                                contract=manifest.get("qualification_contract"))
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

    The wave size and the qualification flag come from the config that Task 8P1 froze; the posture is
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
    """The port the existing parallel worker dispatches to for a fixed ACT collection wave.

    It follows the same shape as `ActCollectionWorkload`: the worker sees a `kind` and a
    `run_authorized` call, and every decision about *what* to collect stays inside the campaign, so the
    worker cannot widen a wave or re-collect a sealed scene.
    """

    kind = "act_fixed_collection"

    def __init__(self, campaign, *, runtime, boundary=None) -> None:
        self.campaign = campaign
        self.runtime = runtime
        self.boundary = boundary

    def run_authorized(self, lease, *, start_event_id, start_event_type, reset_epoch) -> dict:
        if (not isinstance(lease, dict) or lease.get("admitted") is not True
                or lease.get("start_event_id") != start_event_id
                or lease.get("start_event_type") != start_event_type):
            # the same refusal the runtime adapter makes: no lease, no collection
            raise ValueError("ACT_COLLECTION_LEASE_UNAVAILABLE")
        if lease.get("reset_epoch") != reset_epoch:
            raise ValueError("ACT_COLLECTION_RESET_EPOCH_MISMATCH")
        # the campaign is the executor here: the runtime adapter is its collect port, not this caller's
        if not callable(getattr(self.campaign, "run", None)):
            raise ValueError("ACT_COLLECTION_CAMPAIGN_UNAVAILABLE")
        run = lambda: self.campaign.run()
        outcome = self.boundary(run) if self.boundary is not None else run()
        if not isinstance(outcome, dict) or "campaign_index" not in outcome:
            raise ValueError("ACT_COLLECTION_OUTCOME_INVALID")
        return outcome
