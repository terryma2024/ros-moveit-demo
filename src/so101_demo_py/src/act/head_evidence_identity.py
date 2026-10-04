"""Monitor-neutral canonical identity and bounded JSON validation for Head records."""

import hashlib
import json
import math
import time


_MAX_PAYLOAD = 65536


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def check_deadline(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError('HEAD_MONITOR_IPC_DEADLINE')


def bounded_payload(value, deadline=None):
    """Copy ordinary JSON values with the same bounds used by monitor IPC."""
    budget = _MAX_PAYLOAD
    nodes = 0

    def visit(item, depth):
        nonlocal budget, nodes
        check_deadline(deadline)
        nodes += 1
        if depth > 32 or nodes > _MAX_PAYLOAD // 2 or budget < 0:
            raise ValueError('HEAD_MONITOR_IPC_INPUT_TOO_LARGE')
        kind = type(item)
        owned = item
        if kind is dict:
            if len(item) > _MAX_PAYLOAD // 4:
                raise ValueError('HEAD_MONITOR_IPC_INPUT_TOO_LARGE')
            budget -= 2 + max(0, len(item) - 1) + len(item)
            owned = {}
            for key, nested in item.items():
                if type(key) is not str:
                    raise ValueError('HEAD_MONITOR_IPC_KEY_INVALID')
                owned[visit(key, depth + 1)] = visit(nested, depth + 1)
        elif kind is list:
            if len(item) > _MAX_PAYLOAD // 2:
                raise ValueError('HEAD_MONITOR_IPC_INPUT_TOO_LARGE')
            budget -= 2 + max(0, len(item) - 1)
            owned = [visit(nested, depth + 1) for nested in item]
        elif kind is str:
            if len(item) + 2 > budget:
                raise ValueError('HEAD_MONITOR_IPC_INPUT_TOO_LARGE')
            budget -= 2
            for index, char in enumerate(item):
                if index % 128 == 0:
                    check_deadline(deadline)
                code = ord(char)
                cost = (12 if code > 65535 else 6 if code >= 127 else
                        2 if char in '\\"\b\f\n\r\t' else 6 if code < 32 else 1)
                budget -= cost
                if budget < 0:
                    raise ValueError('HEAD_MONITOR_IPC_INPUT_TOO_LARGE')
        elif kind is bool or item is None:
            budget -= 5
        elif kind is int:
            if not -(2**63) <= item < 2**64:
                raise ValueError('HEAD_MONITOR_IPC_INTEGER_INVALID')
            budget -= len(str(item))
        elif kind is float:
            if not math.isfinite(item):
                raise ValueError('HEAD_MONITOR_IPC_NONFINITE')
            budget -= len(str(item))
        else:
            raise ValueError('HEAD_MONITOR_IPC_TYPE_INVALID')
        if budget < 0:
            raise ValueError('HEAD_MONITOR_IPC_INPUT_TOO_LARGE')
        return owned

    if type(value) is not dict:
        raise ValueError('HEAD_MONITOR_IPC_PAYLOAD_INVALID')
    return visit(value, 0)
