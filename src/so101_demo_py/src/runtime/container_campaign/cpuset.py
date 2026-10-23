"""Opt-in CPU partition of the campaign's containers (campaign config key `shard_cpuset`, absent = off).

With `{"shard_cpus": N, "first_shard_cpu": F}` the shard of worker `wK` gets the logical CPUs `F+K*N .. F+K*N+N-1` (`docker --cpuset-cpus`) and the
Teacher, the Head and the processors get `0 .. F-1`. The Host process itself is not a container and stays where the kernel puts it; it is pinned
from outside if at all. The plan changes where processes may run, never what they compute or what a check accepts."""

from dataclasses import dataclass
import os
import re

_KEY = "shard_cpuset"
_FIELDS = ("shard_cpus", "first_shard_cpu")
#: A `--cpuset-cpus` value as docker takes it: comma-separated CPUs or ascending ranges (checked by `valid_cpu_list`).
_LIST = re.compile(r"\d+(-\d+)?(,\d+(-\d+)?)*")


def valid_cpu_list(value):
    if type(value) is not str or _LIST.fullmatch(value) is None:
        return False
    return all(int(part.split("-")[0]) <= int(part.split("-")[-1]) for part in value.split(","))


def _positive_int(value):
    return type(value) is int and value >= 1


@dataclass(frozen=True, slots=True)
class CpuPlan:
    shard_cpus: int
    first_shard_cpu: int

    def __post_init__(self):
        if not (_positive_int(self.shard_cpus) and _positive_int(self.first_shard_cpu)):
            raise ValueError("CPUSET_PLAN_INVALID")

    def document(self):
        return dict(shard_cpus=self.shard_cpus, first_shard_cpu=self.first_shard_cpu)

    def cpus(self, role, index, *, worker_count, host_cpus=None):
        """The `--cpuset-cpus` value of one role. `index` is the worker's slot number (shards only); the plan must fit the host."""
        if role not in ("head", "teacher", "shard", "processor"):
            raise ValueError("CPUSET_PLAN_ROLE_INVALID")
        host_cpus = os.cpu_count() if host_cpus is None else host_cpus
        if type(worker_count) is not int or worker_count < 1:
            raise ValueError("CPUSET_PLAN_WORKER_INVALID")
        if self.first_shard_cpu + worker_count * self.shard_cpus > host_cpus:
            raise ValueError("CPUSET_PLAN_EXCEEDS_HOST")
        if role != "shard":
            return _range(0, self.first_shard_cpu - 1)
        if type(index) is not int or not 0 <= index < worker_count:
            raise ValueError("CPUSET_PLAN_WORKER_INVALID")
        first = self.first_shard_cpu + index * self.shard_cpus
        return _range(first, first + self.shard_cpus - 1)


def _range(first, last):
    return str(first) if first == last else f"{first}-{last}"


def validate_cpuset(document):
    """The shape of the `shard_cpuset` key; raises ValueError."""
    if type(document) is not dict or set(document) != set(_FIELDS):
        raise ValueError("CPUSET_PLAN_INVALID")
    return CpuPlan(**document)


def cpuset_from_config(config):
    """The `CpuPlan` a campaign config names, or None when the key is absent (off)."""
    if _KEY not in config:
        return None
    return validate_cpuset(config[_KEY])


def worker_index(worker_id):
    match = re.fullmatch(r"w(\d\d+)", worker_id) if type(worker_id) is str else None
    if match is None:
        raise ValueError("CPUSET_PLAN_WORKER_INVALID")
    return int(match.group(1))


def cpus_for(plan, role, *, worker_id=None, worker_count):
    """None when the plan is off; otherwise the role's `--cpuset-cpus` value."""
    if plan is None:
        return None
    return plan.cpus(role, worker_index(worker_id) if role == "shard" else None, worker_count=worker_count)
