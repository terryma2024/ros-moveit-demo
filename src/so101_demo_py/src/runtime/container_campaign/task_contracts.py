"""Small task messages; task_id is the only task attribution field."""

import json
import time
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Closed(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)


class InputRef(_Closed):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @field_validator('path')
    @classmethod
    def absolute_path(cls, value):
        path = PurePosixPath(value)
        if not path.is_absolute() or '..' in path.parts:
            raise ValueError('TASK_INPUT_PATH_INVALID')
        return value


class TaskSpec(_Closed):
    task_id: str = Field(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$')
    inputs_ref: InputRef
    deadline_monotonic_s: float = Field(gt=0, allow_inf_nan=False)


class TaskStatus(_Closed):
    task_id: str = Field(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$')
    state: Literal['ACCEPTED', 'RUNNING', 'SUCCEEDED', 'FAILED']
    fault_reason: str | None = Field(default=None, min_length=1, max_length=300)


class InstanceStatus(_Closed):
    instance_id: str = Field(min_length=1, max_length=200)
    state: Literal['STARTING', 'READY', 'BUSY', 'STOPPING', 'TERMINATED']
    task: TaskStatus | None = None
    fault_reason: str | None = Field(default=None, min_length=1, max_length=300)
    resources_released: bool = False

    @model_validator(mode='after')
    def released_only_after_exit(self):
        if self.resources_released and self.state != 'TERMINATED':
            raise ValueError('TASK_RESOURCES_NOT_TERMINATED')
        return self


class _StatusQuery(_Closed):
    task_id: str | None = Field(default=None, pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$')


class _Terminate(_Closed):
    reason: str = Field(min_length=1, max_length=300)


class TaskRequest(_Closed):
    operation: Literal['assign_task', 'get_status', 'terminate']
    deadline_ns: int = Field(gt=0)
    payload: dict

    @model_validator(mode='after')
    def closed_payload(self):
        model = {'assign_task': TaskSpec, 'get_status': _StatusQuery,
                 'terminate': _Terminate}[self.operation]
        model.model_validate(self.payload)
        return self

    def check_deadline(self, now_ns):
        if self.deadline_ns <= now_ns:
            raise ValueError('TASK_REQUEST_DEADLINE_EXPIRED')
        if (self.operation == 'assign_task'
                and self.payload['deadline_monotonic_s'] <= now_ns/1e9):
            raise ValueError('TASK_DEADLINE_EXPIRED')


def _unique_fields(pairs):
    document = {}
    for key, value in pairs:
        if key in document:
            raise ValueError('TASK_DUPLICATE_FIELD')
        document[key] = value
    return document


def _reject_constant(_value):
    raise ValueError('TASK_NOT_FINITE')


def decode_task_request(raw, *, max_bytes, now_ns=None):
    if type(raw) is not bytes or type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError('TASK_FRAME_INVALID')
    if not raw or len(raw) > max_bytes:
        raise ValueError('TASK_FRAME_OVERSIZE')
    document = json.loads(raw, object_pairs_hook=_unique_fields,
                          parse_constant=_reject_constant)
    packet = TaskRequest.model_validate(document)
    packet.check_deadline(time.monotonic_ns() if now_ns is None else now_ns)
    return packet
