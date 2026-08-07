"""Normalize deterministic CLI behavior without runtime dependencies."""

import subprocess
import sys


def run_behavior(arguments: list[str]) -> dict:
    completed=subprocess.run([sys.executable,"-m","so101_gazebo_demo_py.cli.pick_place_state_machine",*arguments],text=True,capture_output=True,check=False)
    fields={}
    for line in completed.stdout.splitlines():
        if "=" in line:
            key,value=line.split("=",1); fields[key]=value
    return {
        "exit_code":completed.returncode,
        "status":fields.get("status"),
        "current_state":fields.get("current_state"),
        "next_state":fields.get("next_state"),
        "failure_code":fields.get("failure"),
        "state_trace":fields.get("state_trace","").split(",") if fields.get("state_trace") else [],
    }
