"""The instance spec: the immutable document the Host writes for one ACT instance, and its loader.

Every launcher hands the same spec to the same program. The loader proves the document's shape, identities and hashes before
anything is created, and returns it together with the frozen parallel runtime config the instance runs under.
"""

import json
import math
import re
import time

from so101_demo.runtime.container_campaign.paths import _path
from so101_demo.runtime.inference.config import _open_regular, validate_file_ref, calibration_runtime_hash
from so101_demo.runtime.parallel_ipc.frames import _pairs


SPEC_SCHEMA_VERSION = 2
_FIELDS = {"schema_version", "kind", "workload_kind", "campaign_id", "worker_id", "launch_generation",
    "execution_generation", "runtime_id", "service_epoch", "service_token", "owned_root",
    "simulation_session_id", "gpu_uuid", "controlled_runtime"}
_COLLECTION_FIELDS={'business_identity','parallel_runtime','campaign_config','wave_id','deadline_monotonic_s'}
_BUSINESS_FIELDS={'manifest_sha256','runtime_config_sha256','collection_config_sha256','contact_policy_fingerprint'}


def instance_rig(spec):
    """The camera rig of an instance: the one its campaign config names (absent = the default rig). A spec without a campaign
    config (a readiness shard, a rollout) is the default rig."""
    from so101_demo.act.rig_profile import DEFAULT_RIG, rig_from_profile_sha256

    reference = spec.get("campaign_config") if isinstance(spec, dict) else None
    if reference is None:
        return DEFAULT_RIG
    from so101_demo.runtime.inference.config import load_campaign_config
    campaign = load_campaign_config(validate_file_ref(reference), roles=("teacher",), expected_sha256=reference["sha256"])
    return rig_from_profile_sha256(campaign.get("rig_profile_sha256"))


def load_spec(path):
    from so101_demo.cli.mujoco_batch.request import _load_runtime_config

    try:
        with _open_regular(path) as stream:
            raw = stream.read(1024*1024+1)
        if len(raw)>1024*1024:
            raise ValueError("size")
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("nonfinite")))
        if type(document) is not dict:raise ValueError('shape/kind')
        collection=document.get('workload_kind')=='act_collection'
        expected=_FIELDS|_COLLECTION_FIELDS if collection else _FIELDS
        if (set(document) != expected
                or type(document["schema_version"]) is not int or document["schema_version"] != SPEC_SCHEMA_VERSION
                or document["kind"] != "ACT_CONTAINER_SHARD"
                or document["workload_kind"] not in ("no_motion_readiness",'act_collection')):
            raise ValueError("shape/kind")
        for name in ("campaign_id", "worker_id", "runtime_id", "service_epoch", "simulation_session_id"):
            if type(document[name]) is not str or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", document[name]) is None:
                raise ValueError("identity")
        for name in ("launch_generation", "execution_generation"):
            if type(document[name]) is not int or document[name]<=0:
                raise ValueError("generation")
        if (type(document["service_token"]) is not str or re.fullmatch(r"[0-9a-f]{64}", document["service_token"]) is None
                or type(document["gpu_uuid"]) is not str or re.fullmatch(r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",document["gpu_uuid"]) is None):
            raise ValueError("token/device")
        root = _path(document["owned_root"], directory=True)
        if root.name != f"g{document['launch_generation']}" or root.parent.name != document["worker_id"]:
            raise ValueError("private root scope")
        runtime_path = validate_file_ref(document["controlled_runtime"])
        if collection:
            from so101_demo.runtime.inference.config import load_campaign_config
            identity=document['business_identity']
            if (type(identity) is not dict or set(identity)!=_BUSINESS_FIELDS
                    or any(type(value) is not str or re.fullmatch(r'[0-9a-f]{64}',value) is None
                           for value in identity.values())
                    or identity['runtime_config_sha256']!=document['controlled_runtime']['sha256']
                    or document['wave_id']!=root.parent.parent.name
                    or re.fullmatch(r'wave-[0-9]+',document['wave_id']) is None
                    or type(document['deadline_monotonic_s']) not in (int,float)
                    or not math.isfinite(document['deadline_monotonic_s'])
                    or document['deadline_monotonic_s']<=time.monotonic()):
                raise ValueError('collection identity')
            campaign=load_campaign_config(validate_file_ref(document['campaign_config']),roles=('teacher',),
                expected_sha256=document['campaign_config']['sha256'])
            if (campaign['controlled_runtime']!=document['controlled_runtime']
                    or campaign['gpu_uuid']!=document['gpu_uuid']):
                raise ValueError('collection campaign drift')
            runtime = _load_runtime_config(validate_file_ref(document['parallel_runtime']))
        else:
            runtime = _load_runtime_config(runtime_path)
        if calibration_runtime_hash(runtime_path) != document["controlled_runtime"]["sha256"]:
            raise ValueError("runtime drift")
        return document, runtime
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, UnicodeError) as error:
        raise ValueError("CAMPAIGN_SHARD_SPEC_INVALID") from error
