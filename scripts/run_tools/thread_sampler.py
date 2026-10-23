#!/usr/bin/env python3
"""Independent 10 Hz per-thread scheduler stall sampler for SO-101 container collection runs (EXP-595).

Standalone: standard library only, no ROS, no repository imports. A run script starts it right after host_sampler.py and stops it
(SIGTERM) after the collection CLI. It writes only new files under --out-dir:
  thread-sampler-<stamp>-<pid>.jsonl         rows (below)
  thread-sampler-<stamp>-<pid>.meta.json     start record
  thread-sampler-<stamp>-<pid>.summary.json  written at stop (also on SIGTERM); its absence means the sampler did not stop cleanly

Every row has `k` (kind), `seq` (tick number) and, on tick rows, `t_wall_ns` / `t_mono_ns`. All durations are nanoseconds unless the key
ends in `_ms`. Counters are raw cumulative kernel values; `d*` keys are deltas since the same thread's previous tick.

Row kinds
  start  first line: argv, tunables, scheduling.
  tick   one per tick: `late_ms` (start lateness against the monotonic schedule), `cost_ms` (time spent producing the tick), `host` =
         {"pressure": {"cpu"|"memory"|"io": {"some": [avg10, total_us], "full": [...]}}, "procs_running", "procs_blocked", "ctxt"}.
  skip   written when the sampler fell behind: `missed` schedule slots were dropped (no burst to catch up).
  ev     container discovery events: appear / gone / error.
  c      one per container per tick: `dt_ms` since the container's previous tick, `n_thr`, `born`, `died`, `cpu` (cpu.stat: usage_usec,
         user_usec, system_usec, nr_periods, nr_throttled, throttled_usec, ...), `psi` ({"cpu"|"io"|"memory": {"some": [avg10, total_us],
         "full": [...]}}), `err` (names of cgroup files that could not be read).
  p      once per pid: `cmd` (shortened command line).
  t      only for a thread with run-queue delay delta >= --wait-ms, cpu time delta >= --run-ms, or state D: `pid`, `tid`, `comm`,
         `r` (reasons: w=wait, r=run, D), `st` (state letter when read this tick, else null), `span` (ticks since this thread was last read: more than 1 for a
         thread that had been idle and was read at the reduced cold rate; the deltas cover all of them), `dr` (on-cpu ns), `dw` (run-queue delay ns),
         `dsl` (timeslices), `wait_total` / `run_total` (cumulative ns).
  (t rows are capped per container and per tick; the c row's `t_dropped` counts the threads that met a threshold but got no row.)
  s      once per --snapshot-interval per (pid, comm) group per container: `n` threads, `run`/`wait`/`sl` = SUMS OF THE PER-TICK DELTAS over
         the snapshot interval, `max_dw` / `max_dr` = largest single-tick delta of one thread, `vol` / `nonvol` = context-switch deltas
         since the previous snapshot, `st` = {state: thread count} at the snapshot, `wait_total` / `run_total` cumulative sums.

Run-queue delay is the second field of /proc/<pid>/task/<tid>/schedstat: time the thread was runnable and waiting for a CPU. Time blocked
(sleeping, D) is not in it; a thread that is slow while its run-queue delay stays small was blocked, not starved. cgroup `nr_throttled` /
`throttled_usec` count CFS bandwidth throttling of the whole container.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import resource
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

CGROUP_ROOT = Path("/sys/fs/cgroup")
PROC = "/proc"
NAME_PREFIX = "so101-act-"
CPU_STAT_KEYS = ("usage_usec", "user_usec", "system_usec", "nr_periods", "nr_throttled", "throttled_usec")
PSI_FILES = (("cpu", "cpu.pressure"), ("io", "io.pressure"), ("memory", "memory.pressure"))
CMD_LIMIT = 160
READ_BYTES = 1 << 18


def read_file(path) -> bytes:
    fd = os.open(path, os.O_RDONLY)
    try:
        return os.read(fd, READ_BYTES)
    finally:
        os.close(fd)


def parse_psi(data: bytes) -> dict:
    """`some avg10=0.00 avg60=.. avg300=.. total=123` lines into {"some": [avg10, total]}."""
    out = {}
    for line in data.decode(errors="replace").splitlines():
        parts = line.split()
        if not parts:
            continue
        fields = dict(item.partition("=")[::2] for item in parts[1:])
        out[parts[0]] = [float(fields.get("avg10", 0.0)), int(fields.get("total", 0))]
    return out


def parse_cpu_stat(data: bytes) -> dict:
    out = {}
    for line in data.decode(errors="replace").splitlines():
        key, _, value = line.partition(" ")
        if key in CPU_STAT_KEYS:
            out[key] = int(value)
    return out


def parse_status(data: bytes) -> dict:
    """Name, State, Tgid and the two context-switch counters of /proc/<pid>/task/<tid>/status, found by offset rather than by line."""
    out = {}
    try:
        out["Name"] = data[6:data.index(b"\n")].decode(errors="replace")
        i = data.index(b"\nState:\t") + 8
        out["State"] = data[i:i + 1].decode()
        i = data.index(b"\nTgid:\t") + 7
        out["Tgid"] = data[i:data.index(b"\n", i)].decode()
        i = data.index(b"\nvoluntary_ctxt_switches:\t") + 26
        out["voluntary_ctxt_switches"] = data[i:data.index(b"\n", i)].decode()
        i = data.index(b"\nnonvoluntary_ctxt_switches:\t") + 29
        out["nonvoluntary_ctxt_switches"] = data[i:data.index(b"\n", i)].decode()
    except ValueError:
        pass
    return out


def host_row() -> dict:
    row = {}
    pressure = {}
    for name in ("cpu", "memory", "io"):
        try:
            pressure[name] = parse_psi(read_file(f"{PROC}/pressure/{name}"))
        except OSError:
            pass
    row["pressure"] = pressure
    try:
        for line in read_file(f"{PROC}/stat").decode(errors="replace").splitlines():
            if line.startswith(("procs_running", "procs_blocked", "ctxt")):
                key, value = line.split()
                row[key] = int(value)
    except OSError:
        pass
    return row


class Thread:
    """One sampled thread. `run`/`wait`/`slices` are the latest cumulative schedstat values; `snap_*` the values at the last snapshot,
    so a snapshot sum is a subtraction rather than a per-tick accumulation. `max_dw`/`max_dr` are the largest single-tick deltas since then."""
    __slots__ = ("tid", "pid", "comm", "fd_sched", "fd_stat", "run", "wait", "slices", "snap_run", "snap_wait", "snap_sl", "max_dw",
                 "max_dr", "vol", "nonvol", "snap_vol", "snap_nonvol", "state", "raw", "idle", "cold", "last_seq")

    def __init__(self, tid, pid, comm):
        self.tid, self.pid, self.comm = tid, pid, comm
        self.fd_sched = self.fd_stat = -1
        self.run = self.wait = self.slices = self.snap_run = self.snap_wait = self.snap_sl = self.max_dw = self.max_dr = 0
        self.vol = self.nonvol = self.snap_vol = self.snap_nonvol = 0
        self.state = "?"
        self.raw = b""
        self.idle = 0                   # consecutive reads whose schedstat did not change
        self.cold = False               # idle long enough to be read only every --cold-every ticks
        self.last_seq = 0

    def close(self):
        for name in ("fd_sched", "fd_stat"):
            fd = getattr(self, name)
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
                setattr(self, name, -1)


class Target:
    """One sampled unit: a docker container cgroup (threads from cgroup.threads) or a plain process (threads from /proc/<pid>/task)."""

    def __init__(self, name, cgroup=None, pid=None, container_id=None):
        self.name, self.cgroup, self.pid, self.container_id = name, cgroup, pid, container_id
        self.threads = {}               # tid -> Thread
        self.cmds = {}                  # pid -> shortened cmdline (emitted once)
        self.dead = {}                  # (pid, comm) -> [run, wait, sl, vol, nonvol, max_dw, max_dr] of threads that exited this window
        self.state_buckets = None       # tid % state_every -> {tid: Thread}
        self.status_buckets = None      # tid % window ticks -> {tid: Thread}
        self.cg_fds = {}                # file name -> fd
        self.prev_mono = None
        self.gone = False
        self.cpu_stat_last = {}

    def open_cgroup_files(self):
        if self.cgroup is None:
            return
        for name in ("cgroup.threads", "cpu.stat", "cpu.pressure", "io.pressure", "memory.pressure"):
            try:
                self.cg_fds[name] = os.open(self.cgroup / name, os.O_RDONLY)
            except FileNotFoundError:
                if not self.cgroup.is_dir():
                    raise
            except OSError:
                pass

    def close(self):
        for thread in self.threads.values():
            thread.close()
        for fd in self.cg_fds.values():
            try:
                os.close(fd)
            except OSError:
                pass
        self.threads.clear()
        self.cg_fds.clear()

    def read_cg(self, name):
        fd = self.cg_fds.get(name)
        if fd is None:
            return None
        return os.pread(fd, READ_BYTES, 0)

    def current_tids(self) -> set:
        if self.cgroup is not None:
            data = self.read_cg("cgroup.threads")
            if data is None:
                raise FileNotFoundError(errno.ENOENT, "cgroup.threads")
            return {int(value) for value in data.split()}
        tids = {int(value) for value in os.listdir(f"{PROC}/{self.pid}/task")}
        data = read_file(f"{PROC}/{self.pid}/stat")
        if not tids or data[data.rindex(b")") + 2:][:1] == b"Z":      # a zombie keeps its /proc entry but has exited
            raise FileNotFoundError(errno.ESRCH, "process has exited")
        return tids


class Sampler:
    def __init__(self, options, stop):
        self.o, self.stop = options, stop
        self.targets = {}
        self.lock = threading.Lock()
        self.pending = {}                # discovery result: name -> (id, cgroup) handed to the main loop
        self.removed = set()
        self.errors = {"discovery": 0, "thread_read": 0, "target_read": 0, "fd_limit": 0}
        self.events = []
        self.rows = {}
        self.bytes = 0
        self.cmd_cache = {}
        self.row_budget = 0
        self.window = max(1, round(options.snapshot_interval / options.interval))

    # ---- discovery (own thread: a slow Docker must never delay a tick) -------------------------------------------------------------
    def docker(self, *argv, timeout=10):
        return subprocess.run(("docker", *argv), capture_output=True, text=True, timeout=timeout, check=True).stdout

    def locate(self, container_id, pid):
        for candidate in (CGROUP_ROOT / "system.slice" / f"docker-{container_id}.scope", CGROUP_ROOT / "docker" / container_id):
            if candidate.is_dir():
                return candidate
        try:
            for line in read_file(f"{PROC}/{pid}/cgroup").decode().splitlines():
                if line.startswith("0::"):
                    return CGROUP_ROOT / line[3:].lstrip("/")
        except OSError:
            pass
        return None

    def discover_once(self, timeout=10):
        listing = self.docker("ps", "--no-trunc", "--filter", f"name={self.o.name_prefix}", "--format", "{{.ID}} {{.Names}}",
                              timeout=timeout)
        seen = {}
        for line in listing.splitlines():
            container_id, _, name = line.partition(" ")
            if name.startswith(self.o.name_prefix):
                seen[name] = container_id
        with self.lock:
            known = {name: (t.container_id, t.cgroup) for name, t in self.targets.items() if t.container_id is not None}
            known.update({name: value for name, value in self.pending.items()})
        for name, container_id in seen.items():
            if name in known and known[name][0] == container_id and known[name][1] is not None and known[name][1].is_dir():
                continue
            try:
                pid = int(self.docker("inspect", "--format", "{{.State.Pid}}", container_id).strip())
            except (subprocess.SubprocessError, ValueError, OSError):
                self.errors["discovery"] += 1
                continue
            directory = self.locate(container_id, pid)
            if directory is not None:
                with self.lock:
                    self.pending[name] = (container_id, directory)
        with self.lock:
            for name, (container_id, _) in known.items():
                if name not in seen:
                    self.removed.add(name)

    def discovery_loop(self):
        while not self.stop.is_set():
            try:
                self.discover_once()
            except (subprocess.SubprocessError, OSError):
                self.errors["discovery"] += 1
            self.stop.wait(self.o.discover_interval)

    # ---- thread handling -------------------------------------------------------------------------------------------------------------
    def add_thread(self, target, tid, out):
        """Returns the Thread (baseline taken now) or None if it vanished. The thread's pid comes from /proc/<tid>/status."""
        try:
            status = parse_status(read_file(f"{PROC}/{tid}/status"))
            pid = int(status["Tgid"])
        except (OSError, KeyError, ValueError):
            return None
        thread = Thread(tid, pid, status.get("Name", "?"))
        base = f"{PROC}/{pid}/task/{tid}"
        try:
            thread.fd_sched = os.open(base + "/schedstat", os.O_RDONLY)
            thread.raw = os.pread(thread.fd_sched, 128, 0)
            thread.run, thread.wait, thread.slices = (int(v) for v in thread.raw.split()[:3])
            thread.fd_stat = os.open(base + "/stat", os.O_RDONLY)
        except OSError as error:
            thread.close()
            if error.errno in (errno.EMFILE, errno.ENFILE):
                self.errors["fd_limit"] += 1
            return None
        except ValueError:
            thread.close()
            return None
        thread.state = status.get("State", "?")[:1]
        thread.vol = thread.snap_vol = int(status.get("voluntary_ctxt_switches", 0))
        thread.nonvol = thread.snap_nonvol = int(status.get("nonvoluntary_ctxt_switches", 0))
        thread.snap_run, thread.snap_wait, thread.snap_sl = thread.run, thread.wait, thread.slices   # sums count from first sight
        if pid not in target.cmds:
            cmd = self.cmd_of(pid)
            target.cmds[pid] = cmd
            out.append({"k": "p", "c": target.name, "pid": pid, "cmd": cmd})
        return thread

    def cmd_of(self, pid):
        try:
            text = read_file(f"{PROC}/{pid}/cmdline").replace(b"\0", b" ").decode(errors="replace").strip()
        except OSError:
            return "?"
        return text if len(text) <= CMD_LIMIT else text[:CMD_LIMIT - 3] + "..."

    # ---- one tick --------------------------------------------------------------------------------------------------------------------
    def drop_thread(self, target, tid):
        thread = target.threads.pop(tid, None)
        if thread is None:
            return
        target.state_buckets[tid % self.o.state_every].pop(tid, None)
        target.status_buckets[tid % self.window].pop(tid, None)
        entry = target.dead.setdefault((thread.pid, thread.comm), [0, 0, 0, 0, 0, 0, 0])
        entry[0] += thread.run - thread.snap_run
        entry[1] += thread.wait - thread.snap_wait
        entry[2] += thread.slices - thread.snap_sl
        entry[3] += thread.vol - thread.snap_vol
        entry[4] += thread.nonvol - thread.snap_nonvol
        entry[5] = max(entry[5], thread.max_dw)
        entry[6] = max(entry[6], thread.max_dr)
        thread.close()

    def sample_target(self, target, seq, now_mono, snapshot, out):
        o = self.o
        if target.state_buckets is None:
            target.state_buckets = [{} for _ in range(o.state_every)]
            target.status_buckets = [{} for _ in range(self.window)]
        dt_ns = None if target.prev_mono is None else now_mono - target.prev_mono
        target.prev_mono = now_mono
        try:
            tids = target.current_tids()
        except (OSError, ValueError):
            target.gone = True
            return
        born = died = 0
        threads = target.threads
        for tid in [tid for tid in threads if tid not in tids]:
            self.drop_thread(target, tid)
            died += 1
        for tid in tids:
            if tid not in threads:
                thread = self.add_thread(target, tid, out)
                if thread is not None:
                    threads[tid] = thread
                    target.state_buckets[tid % o.state_every][tid] = thread
                    target.status_buckets[tid % self.window][tid] = thread
                    born += 1
        pread = os.pread
        wait_ns, run_ns = o.wait_ns, o.run_ns
        lost = []
        flagged = []
        cold_every, cold_after = o.cold_every, o.cold_after
        for tid, thread in threads.items():
            if thread.cold and (tid + seq) % cold_every:
                continue
            try:
                raw = pread(thread.fd_sched, 128, 0)
            except OSError:
                lost.append(tid)
                continue
            span = seq - thread.last_seq
            thread.last_seq = seq
            if raw == thread.raw:               # nothing ran and nothing waited since the last read
                thread.idle += 1
                if thread.idle >= cold_after:
                    thread.cold = True
                continue
            thread.idle = 0
            thread.cold = False
            try:
                run, wait, slices = raw.split()[:3]
                run, wait, slices = int(run), int(wait), int(slices)
            except ValueError:
                lost.append(tid)
                continue
            d_run, d_wait = run - thread.run, wait - thread.wait
            d_sl = slices - thread.slices
            thread.run, thread.wait, thread.slices, thread.raw = run, wait, slices, raw
            if d_wait > thread.max_dw:
                thread.max_dw = d_wait
            if d_run > thread.max_dr:
                thread.max_dr = d_run
            if d_wait >= wait_ns or d_run >= run_ns:
                flagged.append((thread, d_run, d_wait, d_sl, span))
        for tid in lost:
            self.drop_thread(target, tid)
            died += 1
        seen_flag = set()
        dropped = 0
        container_rows = 0
        flagged.sort(key=lambda item: -max(item[1], item[2]))     # the worst threads first when the row cap bites
        for thread, d_run, d_wait, d_sl, span in flagged:
            if container_rows >= o.max_rows_container or self.row_budget <= 0:
                dropped += 1
                seen_flag.add(thread.tid)
                continue
            container_rows += 1
            self.row_budget -= 1
            reasons = ("w" if d_wait >= wait_ns else "") + ("r" if d_run >= run_ns else "")
            state = self.read_state(thread)
            if state == "D":
                reasons += "D"
            seen_flag.add(thread.tid)
            out.append({"k": "t", "seq": seq, "c": target.name, "pid": thread.pid, "tid": thread.tid, "comm": thread.comm, "r": reasons,
                        "st": state, "span": span, "dr": d_run, "dw": d_wait, "dsl": d_sl, "wait_total": thread.wait, "run_total": thread.run})
        for thread in list(target.state_buckets[seq % o.state_every].values()):     # D detection at 1/state_every of the tick rate
            if thread.tid not in seen_flag and self.read_state(thread) == "D":
                if container_rows >= o.max_rows_container or self.row_budget <= 0:
                    dropped += 1
                    continue
                container_rows += 1
                self.row_budget -= 1
                out.append({"k": "t", "seq": seq, "c": target.name, "pid": thread.pid, "tid": thread.tid, "comm": thread.comm,
                            "r": "D", "st": "D", "span": 0, "dr": 0, "dw": 0, "dsl": 0, "wait_total": thread.wait, "run_total": thread.run})
        cold_window = (seq // self.window) % o.cold_every          # an idle (cold) thread's status is read one window in cold_every
        for thread in list(target.status_buckets[seq % self.window].values()):      # context switches, name, state: 1/window of threads
            if thread.cold and cold_window:
                continue
            try:
                status = parse_status(read_file(f"{PROC}/{thread.pid}/task/{thread.tid}/status"))
                thread.comm = status.get("Name", thread.comm)
                thread.state = status.get("State", thread.state)
                thread.vol = int(status.get("voluntary_ctxt_switches", thread.vol))
                thread.nonvol = int(status.get("nonvoluntary_ctxt_switches", thread.nonvol))
            except (OSError, ValueError):
                pass
        row = {"k": "c", "seq": seq, "c": target.name, "dt_ms": None if dt_ns is None else round(dt_ns / 1e6, 2),
               "n_thr": len(threads), "born": born, "died": died}
        if dropped:
            row["t_dropped"] = dropped
        if target.cgroup is not None:
            errors = []
            try:
                data = target.read_cg("cpu.stat")
                if data is None:
                    errors.append("cpu.stat")
                else:
                    row["cpu"] = parse_cpu_stat(data)
                psi = {}
                for key, name in PSI_FILES:
                    data = target.read_cg(name)
                    if data is None:
                        errors.append(name)
                    else:
                        psi[key] = parse_psi(data)
                row["psi"] = psi
            except OSError:
                target.gone = True
            if errors:
                row["err"] = errors
        out.append(row)
        if snapshot:
            self.snapshot(target, seq, out)

    def read_state(self, thread):
        try:
            data = os.pread(thread.fd_stat, 512, 0)
            thread.state = data[data.rindex(b")") + 2:][:1].decode()
            return thread.state
        except (OSError, ValueError):
            return None

    def snapshot(self, target, seq, out):
        """Per (pid, comm): n threads, on-cpu / run-queue delay / timeslice and context-switch sums over the window, the state mix and the
        largest single-tick deltas. Pure arithmetic on values already read; the only I/O of the window was spread over its ticks."""
        groups = {}
        for thread in target.threads.values():
            entry = groups.get((thread.pid, thread.comm))
            if entry is None:
                entry = groups[(thread.pid, thread.comm)] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, {}]
            entry[0] += 1
            entry[1] += thread.run - thread.snap_run
            entry[2] += thread.wait - thread.snap_wait
            entry[3] += thread.slices - thread.snap_sl
            entry[4] += thread.vol - thread.snap_vol
            entry[5] += thread.nonvol - thread.snap_nonvol
            if thread.max_dw > entry[6]:
                entry[6] = thread.max_dw
            if thread.max_dr > entry[7]:
                entry[7] = thread.max_dr
            entry[8] += thread.wait
            entry[9] += thread.run
            entry[10][thread.state] = entry[10].get(thread.state, 0) + 1
            thread.snap_run, thread.snap_wait, thread.snap_sl = thread.run, thread.wait, thread.slices
            thread.snap_vol, thread.snap_nonvol = thread.vol, thread.nonvol
            thread.max_dw = thread.max_dr = 0
        for key, gone in target.dead.items():
            entry = groups.get(key)
            if entry is None:
                entry = groups[key] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, {}]
            entry[1] += gone[0]
            entry[2] += gone[1]
            entry[3] += gone[2]
            entry[4] += gone[3]
            entry[5] += gone[4]
            entry[6] = max(entry[6], gone[5])
            entry[7] = max(entry[7], gone[6])
        target.dead = {}
        for (pid, comm), e in sorted(groups.items()):
            out.append({"k": "s", "seq": seq, "c": target.name, "pid": pid, "comm": comm, "n": e[0], "run": e[1], "wait": e[2],
                        "sl": e[3], "vol": e[4], "nonvol": e[5], "max_dw": e[6], "max_dr": e[7], "wait_total": e[8], "run_total": e[9],
                        "st": e[10]})

    def sync_targets(self, out):
        with self.lock:
            pending, self.pending = self.pending, {}
            removed, self.removed = self.removed, set()
        for name in removed:
            target = self.targets.pop(name, None)
            if target is not None and target.container_id is not None:
                target.close()
                out.append({"k": "ev", "event": "gone", "c": name})
        for name, (container_id, directory) in pending.items():
            old = self.targets.get(name)
            if old is not None:
                if old.container_id == container_id:
                    continue
                old.close()
            target = Target(name, cgroup=directory, container_id=container_id)
            try:
                target.open_cgroup_files()
            except OSError as error:
                out.append({"k": "ev", "event": "error", "c": name, "error": repr(error)[:120]})
                continue
            self.targets[name] = target
            out.append({"k": "ev", "event": "appear", "c": name, "id": container_id, "cgroup": str(directory.relative_to(CGROUP_ROOT))
                        if directory.is_relative_to(CGROUP_ROOT) else str(directory)})


def write_json(directory: Path, name: str, document: dict) -> None:
    temporary = directory / (name + ".partial")
    with open(temporary, "w") as stream:
        json.dump(document, stream, sort_keys=True, indent=2)
        stream.write("\n")
    os.replace(temporary, directory / name)


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


def raise_fd_limit() -> dict:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    want = hard if hard != resource.RLIM_INFINITY else 1 << 20
    if soft < want:
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (want, hard))
        except (OSError, ValueError):
            pass
    return {"nofile_soft": resource.getrlimit(resource.RLIMIT_NOFILE)[0]}


def startup_checks(options, sampler) -> list:
    """Fail closed: every reason the sampler cannot do its job, found before any output file exists."""
    problems = []
    if not CGROUP_ROOT.is_dir() or not (CGROUP_ROOT / "cgroup.controllers").exists():
        problems.append("cgroup v2 is not mounted at /sys/fs/cgroup")
    try:
        tid = threading.get_native_id()
        read_file(f"{PROC}/{os.getpid()}/task/{tid}/schedstat").split()[:3]
        int(read_file(f"{PROC}/{os.getpid()}/task/{tid}/schedstat").split()[1])
    except (OSError, ValueError, IndexError) as error:
        problems.append(f"/proc/<pid>/task/<tid>/schedstat is not readable ({error!r})")
    for name in ("cpu", "memory", "io"):
        try:
            read_file(f"{PROC}/pressure/{name}")
        except OSError as error:
            problems.append(f"/proc/pressure/{name} is not readable ({error!r})")
    if not options.no_docker:
        try:
            sampler.discover_once(timeout=4)
        except (subprocess.SubprocessError, OSError) as error:
            problems.append(f"docker ps failed ({error!r}"[:200] + ")")
    for item in options.extra_cgroup:
        if "=" not in item or not Path(item.split("=", 1)[1]).is_dir():
            problems.append(f"--extra-cgroup {item!r} is not NAME=existing-directory")
    for pid in options.pid:
        if not os.path.isdir(f"{PROC}/{pid}/task"):
            problems.append(f"--pid {pid} does not exist")
    return problems


def percentile(sorted_values, fraction):
    if not sorted_values:
        return None
    return sorted_values[min(len(sorted_values) - 1, int(fraction * len(sorted_values)))]


def run(options) -> int:
    out_dir = Path(options.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda *_: stop.set())
    sampler = Sampler(options, stop)
    problems = startup_checks(options, sampler)
    if problems:
        for problem in problems:
            print("thread_sampler: REFUSED: " + problem, file=sys.stderr)
        return 2
    scheduling = {**pin_and_lower_priority(options.cpu, options.nice), **raise_fd_limit()}
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    base = f"thread-sampler-{stamp}-{os.getpid()}"
    samples = os.fdopen(os.open(out_dir / (base + ".jsonl"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644), "w", buffering=1 << 20)
    started_wall, started_mono = time.time_ns(), time.monotonic_ns()
    cpu_started = resource.getrusage(resource.RUSAGE_SELF)
    tunables = {"interval_s": options.interval, "wait_ms": options.wait_ms, "run_ms": options.run_ms,
                "snapshot_interval_s": options.snapshot_interval, "state_every_ticks": options.state_every,
                "max_rows_container": options.max_rows_container, "max_rows_tick": options.max_rows_tick,
                "cold_after_reads": options.cold_after, "cold_every_ticks": options.cold_every,
                "name_prefix": options.name_prefix, "discover_interval_s": options.discover_interval}
    meta = {"schema": "SO101_THREAD_SAMPLER_META", "schema_version": 1, "pid": os.getpid(), "argv": sys.argv, "t_wall_ns": started_wall,
            "t_mono_ns": started_mono, "scheduling": scheduling, "python": sys.version.split()[0], "samples_file": base + ".jsonl",
            **tunables}
    write_json(out_dir, base + ".meta.json", meta)

    counts = {}
    total_bytes = 0

    def emit(rows):
        nonlocal total_bytes
        if not rows:
            return
        text = "".join(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n" for row in rows)
        for row in rows:
            counts[row["k"]] = counts.get(row["k"], 0) + 1
        samples.write(text)
        total_bytes += len(text)

    emit([{"k": "start", **meta}])
    samples.flush()                       # the run script waits for a non-empty file
    for item in options.extra_cgroup:
        name, directory = item.split("=", 1)
        target = Target(name, cgroup=Path(directory))
        target.open_cgroup_files()
        sampler.targets[name] = target
    for pid in options.pid:
        sampler.targets[f"pid-{pid}"] = Target(f"pid-{pid}", pid=pid)
    if not options.no_docker:
        threading.Thread(target=sampler.discovery_loop, name="sampler-discover", daemon=True).start()

    seq = overruns = skipped_total = 0
    worst_cost_ms = worst_late_ms = 0.0
    costs = []
    next_tick = time.monotonic()
    exit_code = 0
    try:
        while not stop.is_set():
            began = time.monotonic()
            late_ms = max(0.0, (began - next_tick) * 1000.0)
            snapshot = seq % sampler.window == sampler.window - 1
            now_mono = time.monotonic_ns()
            rows = []
            sampler.row_budget = options.max_rows_tick
            sampler.sync_targets(rows)
            head = {"k": "tick", "seq": seq, "t_wall_ns": time.time_ns(), "t_mono_ns": now_mono, "late_ms": round(late_ms, 2),
                    "host": host_row(), "n_targets": len(sampler.targets)}
            rows.insert(0, head)
            for name, target in list(sampler.targets.items()):
                try:
                    sampler.sample_target(target, seq, now_mono, snapshot, rows)
                except Exception as error:      # never let one target stop the sampler
                    sampler.errors["target_read"] += 1
                    rows.append({"k": "ev", "event": "error", "c": name, "error": repr(error)[:160]})
                if target.gone:
                    target.close()
                    del sampler.targets[name]
                    rows.append({"k": "ev", "event": "gone", "c": name})
            cost_ms = (time.monotonic() - began) * 1000.0
            head["cost_ms"] = round(cost_ms, 2)
            emit(rows)
            costs.append(cost_ms)
            worst_cost_ms, worst_late_ms = max(worst_cost_ms, cost_ms), max(worst_late_ms, late_ms)
            seq += 1
            if options.duration is not None and time.monotonic_ns() - started_mono >= options.duration * 1e9:
                break
            next_tick += options.interval
            now = time.monotonic()
            if next_tick <= now:                # fell behind: drop the missed slots, never burst to catch up
                missed = int((now - next_tick) / options.interval) + 1
                overruns += 1
                skipped_total += missed
                next_tick += missed * options.interval
                pending_skip = missed
            else:
                pending_skip = 0
            if pending_skip:
                samples.write(json.dumps({"k": "skip", "seq": seq, "missed": pending_skip}, separators=(",", ":")) + "\n")
            stop.wait(max(0.0, next_tick - time.monotonic()))
    except Exception as error:
        exit_code = 1
        print("thread_sampler: fatal " + repr(error), file=sys.stderr)
    finally:
        samples.flush()
        os.fsync(samples.fileno())
        samples.close()
        stop.set()
        for target in sampler.targets.values():
            target.close()
        cpu_ended = resource.getrusage(resource.RUSAGE_SELF)
        cpu_s = (cpu_ended.ru_utime + cpu_ended.ru_stime) - (cpu_started.ru_utime + cpu_started.ru_stime)
        elapsed_s = (time.monotonic_ns() - started_mono) / 1e9
        costs.sort()
        write_json(out_dir, base + ".summary.json", {
            "schema": "SO101_THREAD_SAMPLER_SUMMARY", "schema_version": 1, "ticks": seq, "overruns": overruns,
            "skipped_slots": skipped_total, "worst_cost_ms": round(worst_cost_ms, 2), "worst_late_ms": round(worst_late_ms, 2),
            "cost_ms_p50": None if not costs else round(percentile(costs, 0.5), 2),
            "cost_ms_p99": None if not costs else round(percentile(costs, 0.99), 2), "errors": sampler.errors,
            "rows": counts, "bytes": total_bytes, "elapsed_s": round(elapsed_s, 3),
            "bytes_per_hour": int(total_bytes / elapsed_s * 3600) if elapsed_s > 0 else None,
            "self_cpu_s": round(cpu_s, 3), "self_cpu_percent_of_one_core": round(100.0 * cpu_s / elapsed_s, 2) if elapsed_s > 0 else None,
            "t_wall_ns": time.time_ns(), "t_mono_ns": time.monotonic_ns(), "stopped_by_signal": stop.is_set() and exit_code == 0,
            "exit_code": exit_code})
    return exit_code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", required=True, help="directory that receives the JSONL, meta and summary files")
    parser.add_argument("--interval", type=float, default=0.1, help="seconds between ticks")
    parser.add_argument("--duration", type=float, default=None, help="stop after this many seconds (default: until SIGTERM)")
    parser.add_argument("--name-prefix", default=NAME_PREFIX, help="container name prefix to sample")
    parser.add_argument("--discover-interval", type=float, default=2.0, help="seconds between docker polls")
    parser.add_argument("--wait-ms", type=float, default=10.0, help="emit a thread row when its run-queue delay delta reaches this")
    parser.add_argument("--run-ms", type=float, default=80.0, help="emit a thread row when its on-cpu delta reaches this")
    parser.add_argument("--snapshot-interval", type=float, default=1.0, help="seconds between per-(pid, comm) snapshots")
    parser.add_argument("--state-every", type=int, default=5,
                        help="read each thread's state (to catch D) once per this many ticks; flagged threads are always read")
    parser.add_argument("--cold-after", type=int, default=10,
                        help="a thread whose schedstat did not change in this many consecutive reads is read only every --cold-every ticks")
    parser.add_argument("--cold-every", type=int, default=5,
                        help="read interval, in ticks, of a thread that has been idle for --cold-after reads (1 disables the saving)")
    parser.add_argument("--max-rows-container", type=int, default=20,
                        help="cap on thread rows per container per tick (the worst by delta are kept; `t_dropped` on the c row counts the rest)")
    parser.add_argument("--max-rows-tick", type=int, default=60, help="cap on thread rows per tick over all containers")
    parser.add_argument("--no-docker", action="store_true", help="test hook: do not poll docker")
    parser.add_argument("--pid", type=int, action="append", default=[], help="test hook: also sample this plain process as pid-<N>")
    parser.add_argument("--extra-cgroup", action="append", default=[], metavar="NAME=DIR", help="test hook: also sample this cgroup")
    parser.add_argument("--cpu", type=int, default=None, help="CPU to pin to (default: the last allowed CPU)")
    parser.add_argument("--nice", type=int, default=10)
    options = parser.parse_args(argv)
    if min(options.interval, options.discover_interval, options.snapshot_interval) <= 0 or options.state_every < 1 or options.cold_every < 1 or options.cold_after < 1:
        parser.error("intervals must be positive and --state-every at least 1")
    options.wait_ns = int(options.wait_ms * 1e6)
    options.run_ns = int(options.run_ms * 1e6)
    return run(options)


if __name__ == "__main__":
    raise SystemExit(main())
