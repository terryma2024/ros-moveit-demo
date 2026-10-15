"""The processor spec: the immutable document the Host writes for one processor, and its loader.

A processor has no GPU, no Teacher and no ROS graph, so its spec is smaller than a shard's. It names the campaign and the
processor slot (`pNN`, a launch generation), the private root (`<run>/processing/pNN/gK`), the run's processing directory under which
every output is written, the frozen parallel runtime config (for the owner-silence and recovery bounds) and a deadline.
"""

import json
import math
import re
import time

from so101_demo.runtime.container_campaign.paths import _path
from so101_demo.runtime.inference.config import _open_regular, validate_file_ref
from so101_demo.runtime.parallel_ipc.frames import _pairs

SPEC_SCHEMA_VERSION = 1
SPEC_KIND = "ACT_CONTAINER_PROCESSOR"
_FIELDS = {"schema_version", "kind", "campaign_id", "processor_id", "launch_generation", "execution_generation",
           "runtime_id", "service_epoch", "service_token", "owned_root", "processing_root", "parallel_runtime",
           "deadline_monotonic_s"}
_ID = r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}"


def load_processor_spec(path):
    """Prove the document's shape, identities and hashes; returns `(spec, runtime_config)`."""
    from so101_demo.cli.mujoco_batch.request import _load_runtime_config

    try:
        with _open_regular(path) as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("size")
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                              parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("nonfinite")))
        if (type(document) is not dict or set(document) != _FIELDS or document["kind"] != SPEC_KIND
                or type(document["schema_version"]) is not int or document["schema_version"] != SPEC_SCHEMA_VERSION):
            raise ValueError("shape/kind")
        for name in ("campaign_id", "runtime_id", "service_epoch"):
            if type(document[name]) is not str or re.fullmatch(_ID, document[name]) is None:
                raise ValueError("identity")
        if type(document["processor_id"]) is not str or re.fullmatch(r"p[0-9]{2}", document["processor_id"]) is None:
            raise ValueError("processor id")
        for name in ("launch_generation", "execution_generation"):
            if type(document[name]) is not int or document[name] <= 0:
                raise ValueError("generation")
        if type(document["service_token"]) is not str or re.fullmatch(r"[0-9a-f]{64}", document["service_token"]) is None:
            raise ValueError("token")
        deadline = document["deadline_monotonic_s"]
        if type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline <= time.monotonic():
            raise ValueError("deadline")
        root = _path(document["owned_root"], directory=True)
        processing = _path(document["processing_root"], directory=True)
        if (root.name != f"g{document['launch_generation']}" or root.parent.name != document["processor_id"]
                or root.parent.parent != processing or processing.name != "processing"):
            raise ValueError("private root scope")
        runtime = _load_runtime_config(validate_file_ref(document["parallel_runtime"]))
        return document, runtime
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, UnicodeError) as error:
        raise ValueError("CAMPAIGN_PROCESSOR_SPEC_INVALID") from error


def processor_launch_id(spec):
    """The Host launch id `processing-pNN-g<launch generation>`."""
    return f"processing-{spec['processor_id']}-g{spec['launch_generation']}"
