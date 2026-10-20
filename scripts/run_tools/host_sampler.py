#!/usr/bin/env python3
"""Independent 1 Hz host and per-container resource sampler for SO-101 collection runs.

Standalone: standard library only, no ROS, no repository imports. A run script starts it before the collection CLI and stops it
(SIGTERM) after. It writes one JSON object per line to a new file under --out-dir and nothing anywhere else.

Every line carries `t_wall_ns` (time.time_ns) and `t_mono_ns` (time.monotonic_ns). Counters are the raw cumulative kernel values;
rates are the reader's job. See README.md next to this file for the schema.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

CGROUP_ROOT = Path("/sys/fs/cgroup")
PROC = Path("/proc")
NAME_PREFIX = "so101-act-"
CGROUP_FILES = ("cpu.stat", "cpu.pressure", "memory.current", "memory.peak", "memory.pressure", "io.stat", "io.pressure",
                "pids.current")
# Substrings of /proc/<pid>/cmdline that pick the processes whose threads' scheduler delay is recorded.
ROLE_MARKERS = (("ros2_control_node", "ros2_control_node"), ("bag_record_entry", "recorder"), ("raw_recorder", "recorder"))
MEMINFO_KEYS = ("MemTotal", "MemFree", "MemAvailable", "Dirty", "Writeback", "SwapTotal", "SwapFree")
VMSTAT_KEYS = ("pgscan_direct", "pswpin", "pswpout", "nr_dirtied", "nr_written", "pgmajfault")
VMSTAT_PREFIXES = ("allocstall",)
DISKSTATS_FIELDS = ("reads", "reads_merged", "sectors_read", "ms_reading", "writes", "writes_merged", "sectors_written",
                    "ms_writing", "ios_in_progress", "ms_io", "weighted_ms_io", "discards", "discards_merged",
                    "sectors_discarded", "ms_discarding", "flushes", "ms_flushing")
GPU_FIELDS = ("utilization.gpu", "utilization.memory", "clocks.sm", "clocks.mem", "power.draw", "temperature.gpu", "memory.used")
GPU_THROTTLE_FIELDS = ("clocks_throttle_reasons.active", "clocks_event_reasons.active")


def read_text(path) -> str:
    with open(path, "r", errors="replace") as stream:
        return stream.read()


def parse_flat_keyed(text: str) -> dict:
    """`key value` lines (cpu.stat, vmstat) into {key: int}."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2:
            try:
                out[parts[0]] = int(parts[1])
            except ValueError:
                pass
    return out


def parse_pressure(text: str) -> dict:
    """`some avg10=0.00 avg60=0.00 avg300=0.00 total=123` lines into {"some": {...}, "full": {...}}."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        fields = {}
        for item in parts[1:]:
            key, _, value = item.partition("=")
            fields[key] = int(value) if key == "total" else float(value)
        out[parts[0]] = fields
    return out


def parse_io_stat(text: str) -> dict:
    """`259:0 rbytes=1 wbytes=2 ...` lines into {"259:0": {"rbytes": 1, ...}}."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        fields = {}
        for item in parts[1:]:
            key, _, value = item.partition("=")
            try:
                fields[key] = int(value)
            except ValueError:
                pass
        out[parts[0]] = fields
    return out


def parse_meminfo(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key in MEMINFO_KEYS:
            out[key + "_kB"] = int(rest.split()[0])
    return out


def parse_proc_stat(text: str) -> dict:
    cpus, extra = {}, {}
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0].startswith("cpu"):
            cpus[parts[0]] = [int(value) for value in parts[1:]]
        elif parts[0] in ("ctxt", "processes", "procs_running", "procs_blocked"):
            extra[parts[0]] = int(parts[1])
    return {"cpu_fields": ["user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal", "guest", "guest_nice"],
            "cpus": cpus, **extra}


def parse_diskstats(text: str, wanted: set) -> dict:
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 14 and parts[2] in wanted:
            values = [int(value) for value in parts[3:]]
            out[parts[2]] = dict(zip(DISKSTATS_FIELDS, values))
    return out


def device_names_under(path: str) -> set:
    """The partition holding `path` and its parent disk, as /proc/diskstats names them (empty when it cannot be resolved)."""
    try:
        info = os.stat(path)
        major, minor = os.major(info.st_dev), os.minor(info.st_dev)
        target = os.path.realpath(f"/sys/dev/block/{major}:{minor}")
    except OSError:
        return set()
    names = {os.path.basename(target)}
    parent = os.path.basename(os.path.dirname(target))
    if os.path.exists(f"/sys/block/{parent}"):
        names.add(parent)
    return names


def cgroup_dir_of_pid(pid: int):
    """The unified-hierarchy cgroup directory of a process, from /proc/<pid>/cgroup (`0::/system.slice/docker-<id>.scope`)."""
    try:
        for line in read_text(PROC / str(pid) / "cgroup").splitlines():
            if line.startswith("0::"):
                return CGROUP_ROOT / line[3:].lstrip("/")
    except OSError:
        pass
    return None


def sample_cgroup(directory: Path) -> dict:
    """Every named cgroup v2 file that exists; a file that cannot be read is listed under `errors`, never raised."""
    out, errors = {}, []
    for name in CGROUP_FILES:
        try:
            text = read_text(directory / name)
        except FileNotFoundError:
            if not directory.exists():
                raise
            errors.append(name)
            continue
        except OSError:
            errors.append(name)
            continue
        if name == "cpu.stat":
            out[name] = parse_flat_keyed(text)
        elif name.endswith(".pressure"):
            out[name] = parse_pressure(text)
        elif name == "io.stat":
            out[name] = parse_io_stat(text)
        else:
            try:
                out[name] = int(text.strip())
            except ValueError:
                out[name] = text.strip()      # memory.peak/ pids.current can read "max"
    if errors:
        out["errors"] = errors
    return out


def classify_pid(pid: int):
    """'ros2_control_node', 'recorder' or None, from the process command line."""
    try:
        cmdline = (PROC / str(pid) / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return None
    for marker, role in ROLE_MARKERS:
        if marker in cmdline:
            return role
    return None


def sample_threads(pid: int) -> list:
    """Scheduler delay per thread: run_ns, wait_ns (runqueue delay) and timeslices from /proc/<pid>/task/<tid>/schedstat."""
    threads = []
    try:
        tids = os.listdir(PROC / str(pid) / "task")
    except OSError:
        return threads
    for tid in tids:
        base = PROC / str(pid) / "task" / tid
        try:
            run_ns, wait_ns, slices = (int(value) for value in read_text(base / "schedstat").split()[:3])
            comm = read_text(base / "comm").strip()
        except (OSError, ValueError):
            continue
        threads.append({"tid": int(tid), "comm": comm, "run_ns": run_ns, "wait_ns": wait_ns, "slices": slices})
    return threads


def sample_processes(directory: Path, roles: dict, rescan: bool) -> dict:
    """{role: {pid: {"threads": [...]}}} for the matching processes inside one cgroup. `roles` caches pid -> role."""
    pids = []
    try:
        pids = [int(value) for value in read_text(directory / "cgroup.procs").split()]
    except OSError:
        return {}
    for pid in list(roles):
        if pid not in pids:
            del roles[pid]
    for pid in pids:
        if rescan or pid not in roles:
            roles[pid] = classify_pid(pid)
    out = {}
    for pid, role in roles.items():
        if role is not None:
            out.setdefault(role, {})[str(pid)] = {"threads": sample_threads(pid)}
    return out


class Containers:
    """so101-act-* containers found by polling `docker ps`/`docker inspect` on its own thread, so a slow Docker never delays a sample."""

    def __init__(self, interval_s: float, prefix: str, extra_cgroups: dict) -> None:
        self.interval_s, self.prefix = interval_s, prefix
        self._lock = threading.Lock()
        self._known = {}            # name -> {"id", "cgroup"}
        self.errors = 0
        self.roles = {}             # name -> pid role cache
        for name, directory in extra_cgroups.items():
            self._known[name] = {"id": None, "cgroup": Path(directory)}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="sampler-discover", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._known)

    def forget(self, name: str) -> None:
        with self._lock:
            self._known.pop(name, None)
            self.roles.pop(name, None)

    def _docker(self, *argv) -> str:
        return subprocess.run(("docker", *argv), capture_output=True, text=True, timeout=10, check=True).stdout

    def _locate(self, container_id: str, pid: int):
        for candidate in (CGROUP_ROOT / "system.slice" / f"docker-{container_id}.scope",
                          CGROUP_ROOT / "docker" / container_id):
            if candidate.is_dir():
                return candidate
        return cgroup_dir_of_pid(pid) if pid > 0 else None

    def _discover(self) -> None:
        listing = self._docker("ps", "--no-trunc", "--filter", f"name={self.prefix}", "--format", "{{.ID}} {{.Names}}")
        seen = {}
        for line in listing.splitlines():
            container_id, _, name = line.partition(" ")
            if name.startswith(self.prefix):
                seen[name] = container_id
        with self._lock:
            known = dict(self._known)
        for name, container_id in seen.items():
            if name in known and known[name]["id"] == container_id and known[name]["cgroup"].is_dir():
                continue
            try:
                pid = int(self._docker("inspect", "--format", "{{.State.Pid}}", container_id).strip())
            except (subprocess.SubprocessError, ValueError, OSError):
                self.errors += 1
                continue
            directory = self._locate(container_id, pid)
            if directory is not None:
                with self._lock:
                    self._known[name] = {"id": container_id, "cgroup": directory}
        with self._lock:                   # a docker container that is no longer listed has gone; extra cgroups stay
            for name in [name for name, item in self._known.items() if item["id"] is not None and name not in seen]:
                del self._known[name]
                self.roles.pop(name, None)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._discover()
            except (subprocess.SubprocessError, OSError):
                self.errors += 1
            self._stop.wait(self.interval_s)


class Gpu:
    """nvidia-smi on its own thread at a lower rate; the sampler reports the latest reading once per reading."""

    def __init__(self, interval_s: float) -> None:
        self.interval_s = interval_s
        self._lock = threading.Lock()
        self._latest = None
        self._reported = None
        self._field_sets = [GPU_FIELDS+(throttle,) for throttle in GPU_THROTTLE_FIELDS]
        self._field_index = 0
        self.errors = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="sampler-gpu", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def take(self):
        with self._lock:
            if self._latest is None or self._latest is self._reported:
                return None
            self._reported = self._latest
            return self._latest

    def _read(self) -> dict:
        fields = self._field_sets[self._field_index]
        began_wall, began_mono = time.time_ns(), time.monotonic_ns()
        result = subprocess.run(["nvidia-smi", "--query-gpu=" + ",".join(fields), "--format=csv,noheader,nounits"],
                                capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            raise subprocess.SubprocessError(result.stderr.strip()[:200])
        values = [item.strip() for item in result.stdout.splitlines()[0].split(",")]
        row = {}
        for field, value in zip(fields, values):
            try:
                row[field] = float(value)
            except ValueError:
                row[field] = value
        return {"t_wall_ns": began_wall, "t_mono_ns": began_mono, "read_ms": round((time.monotonic_ns()-began_mono)/1e6, 1),
                "values": row}

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                reading = self._read()
                with self._lock:
                    self._latest = reading
            except (subprocess.SubprocessError, OSError, IndexError):
                self.errors += 1
                if self._field_index+1 < len(self._field_sets):
                    self._field_index += 1       # the driver names the throttle field differently: try the other name
            self._stop.wait(self.interval_s)


def sample_host(devices: set) -> dict:
    host = {}
    reads = (("proc_stat", lambda: parse_proc_stat(read_text(PROC / "stat"))),
             ("pressure", lambda: {name: parse_pressure(read_text(PROC / "pressure" / name))
                                   for name in ("cpu", "memory", "io")}),
             ("meminfo", lambda: parse_meminfo(read_text(PROC / "meminfo"))),
             ("vmstat", lambda: {key: value for key, value in parse_flat_keyed(read_text(PROC / "vmstat")).items()
                                 if key in VMSTAT_KEYS or key.startswith(VMSTAT_PREFIXES)}),
             ("diskstats", lambda: parse_diskstats(read_text(PROC / "diskstats"), devices)))
    errors = []
    for name, call in reads:
        try:
            host[name] = call()
        except (OSError, ValueError, IndexError):
            errors.append(name)
    if errors:
        host["errors"] = errors
    return host


def pin_and_lower_priority(cpu, nice) -> dict:
    info = {}
    allowed = sorted(os.sched_getaffinity(0))
    target = allowed[-1] if cpu is None else cpu
    if target in allowed:
        os.sched_setaffinity(0, {target})
        info["cpu"] = target
    else:
        info["cpu_error"] = f"cpu {target} not allowed"
    try:
        os.nice(nice)
        info["nice"] = os.getpriority(os.PRIO_PROCESS, 0)
    except OSError as error:
        info["nice_error"] = repr(error)
    return info


def open_new(directory: Path, name: str):
    """Create a new file under `directory`; never overwrite or append to an existing one."""
    descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    return os.fdopen(descriptor, "w", buffering=1)


def write_json(directory: Path, name: str, document: dict) -> None:
    temporary = directory / (name + ".partial")
    with open(temporary, "w") as stream:
        json.dump(document, stream, sort_keys=True, indent=2)
        stream.write("\n")
    os.replace(temporary, directory / name)


def run(options) -> int:
    out_dir = Path(options.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda *_: stop.set())
    scheduling = pin_and_lower_priority(options.cpu, options.nice)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    samples_name = f"host-sampler-{stamp}-{os.getpid()}.jsonl"
    samples = open_new(out_dir, samples_name)
    devices = device_names_under(options.data_path)
    extra = dict(item.split("=", 1) for item in options.extra_cgroup)
    containers = Containers(options.discover_interval, options.name_prefix, extra)
    gpu = None if options.no_gpu else Gpu(options.gpu_interval)
    started_wall, started_mono = time.time_ns(), time.monotonic_ns()
    write_json(out_dir, f"host-sampler-{stamp}-{os.getpid()}.meta.json", {
        "schema": "SO101_HOST_SAMPLER_META", "schema_version": 1, "pid": os.getpid(), "argv": sys.argv,
        "t_wall_ns": started_wall, "t_mono_ns": started_mono, "interval_s": options.interval, "scheduling": scheduling,
        "data_devices": sorted(devices), "samples_file": samples_name, "python": sys.version.split()[0],
        "name_prefix": options.name_prefix, "gpu": not options.no_gpu, "gpu_interval_s": options.gpu_interval})
    containers.start()
    if gpu is not None:
        gpu.start()
    count = overruns = 0
    worst_cost_ms = worst_late_ms = 0.0
    rescan_at = 0.0
    next_tick = time.monotonic()
    try:
        while not stop.is_set():
            began = time.monotonic()
            late_ms = max(0.0, (began-next_tick)*1000.0)
            rescan = began >= rescan_at
            if rescan:
                rescan_at = began+5.0
            line = {"seq": count, "t_wall_ns": time.time_ns(), "t_mono_ns": time.monotonic_ns(), "late_ms": round(late_ms, 2),
                    "host": sample_host(devices), "containers": {}}
            for name, item in containers.snapshot().items():
                directory = item["cgroup"]
                try:
                    entry = {"id": item["id"], "cgroup": str(directory.relative_to(CGROUP_ROOT)), **sample_cgroup(directory)}
                    entry["processes"] = sample_processes(directory, containers.roles.setdefault(name, {}), rescan)
                    line["containers"][name] = entry
                except (FileNotFoundError, NotADirectoryError):
                    containers.forget(name)       # the container vanished between discovery and this read
                    line["containers"][name] = {"gone": True}
                except OSError as error:
                    line["containers"][name] = {"error": repr(error)[:120]}
            if gpu is not None:
                reading = gpu.take()
                if reading is not None:
                    line["gpu"] = reading
            cost_ms = (time.monotonic()-began)*1000.0
            line["cost_ms"] = round(cost_ms, 2)
            samples.write(json.dumps(line, separators=(",", ":"), allow_nan=False) + "\n")
            count += 1
            worst_cost_ms, worst_late_ms = max(worst_cost_ms, cost_ms), max(worst_late_ms, late_ms)
            if options.duration is not None and time.monotonic_ns()-started_mono >= options.duration*1e9:
                break
            next_tick += options.interval
            now = time.monotonic()
            if next_tick <= now:                 # fell behind: skip the missed ticks, never burst to catch up
                overruns += 1
                next_tick = now+options.interval
            stop.wait(max(0.0, next_tick-time.monotonic()))
    finally:
        containers.stop()
        if gpu is not None:
            gpu.stop()
        samples.flush()
        os.fsync(samples.fileno())
        samples.close()
        write_json(out_dir, f"host-sampler-{stamp}-{os.getpid()}.summary.json", {
            "schema": "SO101_HOST_SAMPLER_SUMMARY", "schema_version": 1, "samples": count, "overruns": overruns,
            "worst_cost_ms": round(worst_cost_ms, 2), "worst_late_ms": round(worst_late_ms, 2),
            "discovery_errors": containers.errors, "gpu_errors": None if gpu is None else gpu.errors,
            "t_wall_ns": time.time_ns(), "t_mono_ns": time.monotonic_ns(), "stopped_by_signal": stop.is_set()})
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", required=True, help="directory that receives the JSONL, meta and summary files")
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between samples")
    parser.add_argument("--duration", type=float, default=None, help="stop after this many seconds (default: until SIGTERM)")
    parser.add_argument("--name-prefix", default=NAME_PREFIX, help="container name prefix to sample")
    parser.add_argument("--discover-interval", type=float, default=2.0, help="seconds between docker polls")
    parser.add_argument("--gpu-interval", type=float, default=5.0, help="seconds between nvidia-smi readings")
    parser.add_argument("--no-gpu", action="store_true")
    parser.add_argument("--data-path", default="/data", help="the device holding this path is sampled in /proc/diskstats")
    parser.add_argument("--cpu", type=int, default=None, help="CPU to pin to (default: the last allowed CPU)")
    parser.add_argument("--nice", type=int, default=10)
    parser.add_argument("--extra-cgroup", action="append", default=[], metavar="NAME=DIR",
                        help="also sample this cgroup directory under a given name (test hook; repeatable)")
    options = parser.parse_args(argv)
    if options.interval <= 0 or options.discover_interval <= 0 or options.gpu_interval <= 0:
        parser.error("intervals must be positive")
    return run(options)


if __name__ == "__main__":
    raise SystemExit(main())
