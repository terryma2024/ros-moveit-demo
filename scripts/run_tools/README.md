# Run tools

Standalone samplers that run next to a collection or gate run. They are not product code: they import nothing from the repository, use only the standard library, and write only where you tell them.

- `host_sampler.py`: 1 Hz host and per-container resource sampler (below).
- `thread_sampler.py`: 10 Hz per-thread scheduler stall sampler for container collection runs.
- `memory_sampler.py <logfile>`: appends one line every 30 s with CPU busy %, used and available memory, swap and the biggest process. `scripts/gate/run_host_gate.zsh` starts it when the host config sets `GATE_MEM_SAMPLER=1`.

## host_sampler.py

An independent resource sampler for SO-101 collection runs. A run script starts it before the collection CLI and sends
it SIGTERM after the CLI exits. It is not product code. It imports nothing from the repository, uses only the standard library, and
writes only under the directory given with `--out-dir`.

```
python3 host_sampler.py --out-dir <dir> [--interval 1.0] [--duration S] [--gpu-interval 5] [--no-gpu]
                        [--cpu N] [--nice 10] [--name-prefix so101-act-] [--discover-interval 2]
                        [--data-path /data] [--extra-cgroup NAME=DIR ...]
```

Stop it with SIGTERM or SIGINT. It finishes the current sample, fsyncs the JSONL file and writes the summary file. `--duration`
and `--extra-cgroup` exist for tests: the latter samples a given cgroup directory as if it were a container.

## Files

All names carry the start time and the sampler pid, and each file is created exclusively. The sampler never reuses or appends to an
existing file.

- `host-sampler-<utc>-<pid>.jsonl`: one JSON object per line, one line per sample.
- `host-sampler-<utc>-<pid>.meta.json`: arguments, pid, CPU pin, nice value, the `/proc/diskstats` device names for `/data`.
- `host-sampler-<utc>-<pid>.summary.json`: sample count, overruns, worst per-sample cost and lateness, discovery and GPU error
  counts.

## Cost and behaviour

- It pins itself to one CPU (`os.sched_setaffinity`; default is the last allowed CPU) and raises its nice value by 10.
- A sample of an idle host takes about 1.5 ms. With containers it grows with the number of processes and threads read.
- Timing is fixed to the monotonic clock. A late sample is recorded as `late_ms`. A sample that falls a whole interval behind skips the
  missed tick and counts as an overrun; it never bursts to catch up.
- Docker is polled (`docker ps`, `docker inspect`) on a separate thread, and `nvidia-smi` runs on another. A slow Docker or driver call
  delays no sample.
- A container that exits between discovery and a read is reported once as `{"gone": true}` and then forgotten. A file that cannot be
  read is listed under `errors` for its section. Neither stops the sampler.

## Sample schema

Every line:

| key | meaning |
| --- | --- |
| `seq` | sample number from 0 |
| `t_wall_ns`, `t_mono_ns` | `time.time_ns()` and `time.monotonic_ns()` taken when the sample started |
| `late_ms` | how late this sample started against its schedule |
| `cost_ms` | time spent building this sample |
| `host` | host section, below |
| `containers` | `{container name: container section}`, only containers whose name starts with `so101-act-` |
| `gpu` | present only on the sample that first carries a new `nvidia-smi` reading |

All kernel counters are raw cumulative values. Convert to rates with the timestamps.

`host`:

- `proc_stat`: `cpu_fields` (user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice, in jiffies), `cpus` (`cpu` is the
  total, `cpu0`..`cpuN` are per CPU), and `ctxt`, `processes`, `procs_running`, `procs_blocked`.
- `pressure`: `cpu`, `memory`, `io`, each `{some|full: {avg10, avg60, avg300, total}}` from `/proc/pressure/*`. `total` is in microseconds.
- `meminfo`: `MemTotal_kB`, `MemFree_kB`, `MemAvailable_kB`, `Dirty_kB`, `Writeback_kB`, `SwapTotal_kB`, `SwapFree_kB`.
- `vmstat`: `pgscan_direct`, `pswpin`, `pswpout`, `nr_dirtied`, `nr_written`, `pgmajfault`, and every `allocstall_*`.
- `diskstats`: `{device: {reads, reads_merged, sectors_read, ms_reading, writes, writes_merged, sectors_written, ms_writing,
  ios_in_progress, ms_io, weighted_ms_io, discards, ..., flushes, ms_flushing}}` for the partition under `--data-path` and its parent
  disk.
- `errors`: names of host files that could not be read, if any.

`containers[name]`:

- `id` (full container id), `cgroup` (path below `/sys/fs/cgroup`, found as `system.slice/docker-<id>.scope`, else from
  `/proc/<init pid>/cgroup`).
- `cpu.stat` (dict, includes `usage_usec`, `nr_throttled`, `throttled_usec`), `cpu.pressure`, `memory.pressure`, `io.pressure` (as
  above), `memory.current`, `memory.peak`, `pids.current` (integers, or the text `max`), `io.stat` (`{major:minor: {rbytes, wbytes,
  rios, wios, dbytes, dios}}`).
- `processes`: `{role: {pid: {"threads": [{tid, comm, run_ns, wait_ns, slices}]}}}` for the processes in the container's
  `cgroup.procs` whose command line contains `ros2_control_node` (role `ros2_control_node`) or `bag_record_entry` / `raw_recorder`
  (role `recorder`). `run_ns` is CPU time, `wait_ns` is time spent runnable but waiting for a CPU, and `slices` is the number of
  timeslices, all from `/proc/<pid>/task/<tid>/schedstat`. The pid-to-role map is rebuilt every 5 s.
- `errors`: names of cgroup files that could not be read, if any.
- `{"gone": true}` replaces the whole section for a container that vanished.

`gpu`: `{t_wall_ns, t_mono_ns, read_ms, values}`. `values` holds `utilization.gpu`, `utilization.memory`, `clocks.sm`, `clocks.mem`,
`power.draw`, `temperature.gpu`, `memory.used`, and the throttle bit mask (`clocks_throttle_reasons.active`, or
`clocks_event_reasons.active` on drivers that renamed it). Default rate: one reading every 5 s.

## Example run script fragment

```
set -o pipefail
python3 "$REPO/scripts/run_tools/host_sampler.py" --out-dir "$EVIDENCE/sampler" &
sampler=$!
# ... run the collection CLI ...
kill -TERM $sampler
wait $sampler
```

## Test of 2026-10-14

Twenty seconds on the quiet host with no containers running: 21 samples, 0 overruns, worst cost 1.8 ms, worst lateness 0.13 ms.
A named, exited `so101-act-*` container and a nonexistent cgroup path were tolerated (reported once as `gone`), a real cgroup
(`system.slice/docker.service`) was read in full, and SIGTERM ended a separate run cleanly with its summary written. Per-thread
schedstat parsing was checked against the sampler's own process, since no `ros2_control_node` was available.
