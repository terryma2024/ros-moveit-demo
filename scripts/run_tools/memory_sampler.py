#!/usr/bin/env python3
"""every 30 s: wall time, whole-host CPU busy %, used/available MB, swap MB, biggest process. usage: memory_sampler.py <logfile>
Started by scripts/gate/run_host_gate.zsh when the host config sets GATE_MEM_SAMPLER=1; stopped with SIGTERM."""
import subprocess, sys, time
def cpu():
    v = list(map(int, open('/proc/stat').readline().split()[1:]))
    return sum(v), v[3] + v[4]
def mem():
    m = {l.split(':')[0]: int(l.split()[1]) // 1024 for l in open('/proc/meminfo')}
    return m['MemTotal'] - m['MemAvailable'], m['MemAvailable'], m['SwapTotal'] - m['SwapFree']
pt, pi = cpu()
while True:
    time.sleep(30)
    t, i = cpu(); busy = 100 * ((t - pt) - (i - pi)) / max(1, t - pt); pt, pi = t, i
    used, avail, swap = mem()
    top = subprocess.run("ps -eo rss,comm --sort=-rss | sed -n 2p", shell=True, capture_output=True, text=True).stdout.split()
    with open(sys.argv[1], 'a') as f:
        f.write(f"{time.strftime('%T')} cpu={busy:.0f}% used={used} avail={avail} swap={swap} top={top[1]}:{int(top[0])//1024}M\n")
