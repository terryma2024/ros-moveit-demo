"""The light reachability stack (scripts/reach): container flags of N stacks, the per-call wrapper, the fake simulator's constants and the
rule that decides whether a light stack answers like a full execution stack. Fake `docker` on PATH; no Docker, ROS graph or GPU."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

REACH = Path(__file__).resolve().parents[1] / "reach"
sys.path.insert(0, str(REACH))
COMMIT = "0123456789abcdef0123456789abcdef01234567"
IMAGE = "sha256:" + "a" * 64


def fake_docker(tmp_path, body='printf "%s\\n" "$@" -- >> "$FAKE_DOCKER_LOG"\n'):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    docker = bin_dir / "docker"
    docker.write_text("#!/bin/sh\n" + body)
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_DOCKER_LOG": str(tmp_path / "docker.log")}


def calls(tmp_path):
    path = tmp_path / "docker.log"
    text = path.read_text() if path.exists() else ""
    return [block.splitlines() for block in text.split("--\n") if block.strip()]


@pytest.fixture
def trees(tmp_path):
    root = tmp_path / "mount" / "0123456789ab"
    for name in ("install", "source"):
        (root / name).mkdir(parents=True)
    (root / "source" / "scripts" / "reach").mkdir(parents=True)
    return root / "install", root / "source", tmp_path / "work"


def start(tmp_path, trees, n, *extra):
    install, source, work = trees
    env = fake_docker(tmp_path)
    done = subprocess.run(["zsh", str(REACH / "light_stacks.zsh"), "start", str(n), "--image", IMAGE, "--install", str(install),
                           "--source", str(source), "--work-dir", str(work), "--commit", COMMIT, "--no-wait", *extra],
                          capture_output=True, text=True, env=env)
    return done


def test_each_stack_gets_its_own_name_ros_domain_and_directory_and_none_gets_a_gpu(tmp_path, trees):
    done = start(tmp_path, trees, 3)
    assert done.returncode == 0, done.stderr
    runs = [call for call in calls(tmp_path) if call[0] == "run"]
    assert len(runs) == 3
    names = sorted(call[call.index("--name") + 1] for call in runs)
    assert names == ["reachlight0", "reachlight1", "reachlight2"]
    domains = sorted(next(a for a in call if a.startswith("ROS_DOMAIN_ID=")) for call in runs)
    assert domains == ["ROS_DOMAIN_ID=181", "ROS_DOMAIN_ID=182", "ROS_DOMAIN_ID=183"]
    for call in runs:
        assert "--gpus" not in call and not any("NVIDIA" in a and "graphics" in a for a in call)
        out = [a.split("src=", 1)[1].split(",", 1)[0] for a in call if a.startswith("type=bind,src=") and "readonly" not in a]
        assert len(out) == 1 and Path(out[0]).parent == trees[2]


def test_every_container_restriction_of_the_mounted_start_is_kept_and_the_trees_are_read_only(tmp_path, trees):
    install, source, _work = trees
    done = start(tmp_path, trees, 1)
    assert done.returncode == 0, done.stderr
    (call,) = [c for c in calls(tmp_path) if c[0] == "run"]
    for flag, value in (("--user", "1000:1000"), ("--network", "none"), ("--ipc", "private"), ("--cap-drop", "ALL"),
                        ("--security-opt", "no-new-privileges"), ("--restart", "no")):
        assert call[call.index(flag) + 1] == value, flag
    assert "--read-only" in call and "--privileged" not in call
    assert f"type=bind,src={install},dst={install},readonly" in call
    assert f"type=bind,src={source},dst={source},readonly" in call
    assert f"SO101_EXPECTED_COMMIT={COMMIT}" in call
    assert f"{source}/scripts/reach/light_stack.launch.py" in call[-1] and f"LIGHT_FAKE_SIM={source}/scripts/reach/fake_sim.py" in call


def test_first_domain_and_name_prefix_can_move_and_a_bad_count_is_refused(tmp_path, trees):
    done = start(tmp_path, trees, 2, "--first-domain", "201", "--prefix", "rl")
    assert done.returncode == 0, done.stderr
    runs = [c for c in calls(tmp_path) if c[0] == "run"]
    assert sorted(c[c.index("--name") + 1] for c in runs) == ["rl0", "rl1"]
    assert sorted(next(a for a in c if a.startswith("ROS_DOMAIN_ID=")) for c in runs) == ["ROS_DOMAIN_ID=201", "ROS_DOMAIN_ID=202"]
    for bad in ("0", "33", "x"):
        refused = start(tmp_path / "again", trees, bad)
        assert refused.returncode == 2 and "LIGHT_STACKS_COUNT_INVALID" in refused.stderr


def test_a_missing_tree_or_a_domain_outside_the_ros_range_is_refused_before_docker(tmp_path, trees):
    install, source, work = trees
    install.rmdir()
    done = start(tmp_path, trees, 1)
    assert done.returncode == 2 and "MOUNT_TREE_MISSING" in done.stderr and not calls(tmp_path)
    install.mkdir()
    done = start(tmp_path, trees, 2, "--first-domain", "232")
    assert done.returncode == 2 and "LIGHT_STACKS_DOMAIN_RANGE" in done.stderr and not calls(tmp_path)


def test_stop_removes_exactly_the_named_stacks(tmp_path):
    env = fake_docker(tmp_path)
    done = subprocess.run(["zsh", str(REACH / "light_stacks.zsh"), "stop", "3"], capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr
    removed = [c for c in calls(tmp_path) if c[:2] == ["rm", "-f"]]
    assert sorted(c[2] for c in removed) == ["reachlight0", "reachlight1", "reachlight2"]


def test_the_call_wrapper_executes_task_reachability_in_the_named_container_and_copies_the_evidence_back(tmp_path):
    out = tmp_path / "work" / "s2"
    out.mkdir(parents=True)
    install = tmp_path / "install"
    points = tmp_path / "points.json"
    points.write_text("[]")
    evidence = tmp_path / "res" / "p.json"
    evidence.parent.mkdir()
    body = ('printf "%s\\n" "$@" >> "$FAKE_DOCKER_LOG"; printf -- "--\\n" >> "$FAKE_DOCKER_LOG"\n'
            'for last; do :; done\n'
            'case "$*" in *--evidence-file*) f=$(printf "%s\\n" "$@" | sed -n "/--evidence-file/{n;p}"); echo "{}" > "$f"; echo \'{"reports": []}\';; esac\n')
    env = fake_docker(tmp_path, body)
    done = subprocess.run(["zsh", str(REACH / "reach_call.zsh"), str(out), "reachlight2", "183", str(install), str(points), str(evidence), "sess2"],
                          capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr
    (call,) = [c for c in calls(tmp_path) if c[0] == "exec"]
    assert call[call.index("-e", call.index("ROS_DOMAIN_ID=183") - 1) + 1] == "ROS_DOMAIN_ID=183"
    assert "reachlight2" in call and f"{install}/so101_demo_py/lib/so101_demo_py/task_reachability" in call
    assert call[call.index("--ik-backend") + 1] == "native" and call[call.index("--session-id") + 1] == "sess2"
    assert Path(str(evidence) + ".rc").read_text().strip() == "0"
    assert (out / "calls" / "p.json.points.json").is_file()


def test_the_call_wrapper_passes_a_schema_6_teacher_policy_only_when_one_is_named(tmp_path):
    out = tmp_path / "work" / "s2"
    out.mkdir(parents=True)
    install = tmp_path / "install"
    points = tmp_path / "points.json"
    points.write_text("[]")
    body = ('printf "%s\\n" "$@" >> "$FAKE_DOCKER_LOG"; printf -- "--\\n" >> "$FAKE_DOCKER_LOG"\n'
            'case "$*" in *--evidence-file*) f=$(printf "%s\\n" "$@" | sed -n "/--evidence-file/{n;p}"); echo "{}" > "$f"; echo \'{"reports": []}\';; esac\n')
    for number, policy in enumerate((None, "/act/teacher_execution_policy_side_wrist_fast_carry_b_diversity.yaml")):
        evidence = tmp_path / f"res{number}" / "p.json"
        evidence.parent.mkdir()
        env = fake_docker(tmp_path / f"run{number}", body)
        if policy is not None:
            env["REACH_TEACHER_POLICY"] = policy
        done = subprocess.run(["zsh", str(REACH / "reach_call.zsh"), str(out), "reachlight2", "183", str(install), str(points),
                               str(evidence), "sess2"], capture_output=True, text=True, env=env)
        assert done.returncode == 0, done.stderr
        (call,) = [c for c in calls(tmp_path / f"run{number}") if c[0] == "exec"]
        if policy is None:
            assert "--teacher-execution-policy" not in call
        else:
            assert call[call.index("--teacher-execution-policy") + 1] == policy


def test_the_fake_simulator_publishes_the_joints_of_the_rig_the_launch_file_renders():
    import fake_sim
    import types
    package = types.ModuleType("so101_demo")
    package.__path__ = [str(Path(__file__).resolve().parents[2] / "src" / "so101_demo_py" / "src")]
    sys.modules.setdefault("so101_demo", package)
    from so101_demo.act.rig_profile import DEFAULT_RIG
    from so101_demo.act.joints import ACT_JOINTS, ARM_JOINTS

    expected = list(ACT_JOINTS if DEFAULT_RIG.has_neck else ARM_JOINTS)
    assert list(fake_sim.NAMES) == expected
    assert len(fake_sim.POS) == len(fake_sim.VEL) == len(fake_sim.NAMES)
    assert fake_sim.clock_ns(0.0) == 10_000_000_000 and fake_sim.clock_ns(1.5) == 11_500_000_000


# --- when does a light stack answer like a full stack -------------------------------------------------------------------

def verdict(status, code=None):
    return {"status": status, "first_failure_code": code}


def test_equal_verdicts_pass_and_a_difference_on_a_stable_point_is_a_hard_mismatch():
    from compare_verdicts import compare

    full = [{"a": verdict("REACHABLE"), "b": verdict("UNREACHABLE", "X")}]
    light = [{"a": verdict("REACHABLE"), "b": verdict("REACHABLE")}]
    result = compare(full, light)
    assert result["points"] == 2 and result["equal"] == 1 and result["borderline"] == [] and result["hard_mismatch"] == ["b"]
    assert result["equivalent"] is False


def test_a_difference_is_tolerated_only_where_the_point_flips_between_repeats_on_the_same_stack_kind():
    from compare_verdicts import compare

    full = [{"p": verdict("REACHABLE"), "q": verdict("UNREACHABLE", "X")}, {"p": verdict("UNREACHABLE", "CARTESIAN_CORRIDOR_ORIENTATION"), "q": verdict("UNREACHABLE", "X")}]
    light = [{"p": verdict("REACHABLE"), "q": verdict("UNREACHABLE", "X")}]
    result = compare(full, light)
    assert result["borderline"] == ["p"] and result["hard_mismatch"] == [] and result["equivalent"] is True
    flipping_light = [{"p": verdict("REACHABLE"), "q": verdict("REACHABLE")}, {"p": verdict("REACHABLE"), "q": verdict("UNREACHABLE", "X")}]
    result = compare([{"p": verdict("REACHABLE"), "q": verdict("UNREACHABLE", "X")}], flipping_light)
    assert result["borderline"] == ["q"] and result["equivalent"] is True


def test_a_point_missing_on_one_side_is_a_hard_mismatch_and_nothing_to_compare_is_not_equivalent():
    from compare_verdicts import compare

    assert compare([{"a": verdict("REACHABLE")}], [{"b": verdict("REACHABLE")}])["hard_mismatch"] == ["a", "b"]
    assert compare([], [])["equivalent"] is False


def test_the_command_line_reads_call_outputs_and_exits_one_on_a_hard_mismatch(tmp_path):
    def write(name, rows):
        path = tmp_path / name
        path.write_text(json.dumps({"reports": [{"point_id": k, **v} for k, v in rows.items()]}))
        return str(path)

    full = write("f.json", {"a": verdict("REACHABLE"), "b": verdict("UNREACHABLE", "X")})
    same = write("l.json", {"a": verdict("REACHABLE"), "b": verdict("UNREACHABLE", "X")})
    other = write("m.json", {"a": verdict("REACHABLE"), "b": verdict("REACHABLE")})
    ok = subprocess.run([sys.executable, str(REACH / "compare_verdicts.py"), "--full", full, "--light", same], capture_output=True, text=True)
    assert ok.returncode == 0 and json.loads(ok.stdout)["equivalent"] is True
    bad = subprocess.run([sys.executable, str(REACH / "compare_verdicts.py"), "--full", full, "--light", other], capture_output=True, text=True)
    assert bad.returncode == 1 and json.loads(bad.stdout)["hard_mismatch"] == ["b"]
