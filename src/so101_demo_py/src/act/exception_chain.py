"""A bounded account of an exception and everything it was raised from.

`RecorderInfraError('RECORDER_WRITE_FAILED')` named a wrapper and hid the ValueError that caused it. Every writer and seal failure the
Recorder reports now carries this chain: per link the type, the message (bounded), whether it was the `__cause__` or the `__context__`
of the one before, and the innermost traceback frame of the deepest link.
"""

from __future__ import annotations

import json
import os
import traceback

_MAX_LINKS = 6
_MAX_MESSAGE = 300
_MAX_TEXT = 2000


def describe_chain(error) -> dict:
    links, seen, relation, current = [], set(), "raised", error
    while current is not None and id(current) not in seen and len(links) < _MAX_LINKS:
        seen.add(id(current))
        links.append({"type": type(current).__name__, "message": str(current)[:_MAX_MESSAGE], "relation": relation})
        if current.__cause__ is not None:
            relation, current = "cause", current.__cause__
        elif current.__context__ is not None and not current.__suppress_context__:
            relation, current = "context", current.__context__
        else:
            break
    deepest = error
    for _ in range(_MAX_LINKS):
        following = deepest.__cause__ or (None if deepest.__suppress_context__ else deepest.__context__)
        if following is None or following is deepest:
            break
        deepest = following
    frame = ""
    try:
        frames = traceback.extract_tb(deepest.__traceback__)
        if frames:
            last = frames[-1]
            frame = f"{os.path.basename(last.filename)}:{last.lineno} {last.name}"
    except Exception:  # noqa: BLE001 - observation only
        pass
    return {"links": links, "innermost_frame": frame}


def chain_text(error) -> str:
    """The chain as compact JSON, at most 2000 characters (messages are cut first, then the tail links)."""
    chain = describe_chain(error)
    text = json.dumps(chain, separators=(",", ":"))
    while len(text) > _MAX_TEXT and chain["links"]:
        if len(chain["links"]) > 2:
            chain["links"].pop(1)                      # keep the wrapper and the root cause
        else:
            for link in chain["links"]:
                link["message"] = link["message"][: max(20, len(link["message"]) // 2)]
        text = json.dumps(chain, separators=(",", ":"))
    return text[:_MAX_TEXT]
