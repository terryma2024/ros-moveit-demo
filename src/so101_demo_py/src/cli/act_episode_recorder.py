"""act_episode_recorder: the independent Recorder process, one per attempt.

It records the data side of a Teacher run (RGB, physics chunks, scene_state, world evidence, joint_states and the Teacher
event stream) into an isolated episode directory, seals it and reads it back. It is started before the Teacher and
announces readiness through a ready file; it never commands, cancels, pauses or resets anything.

Exit codes: 0 = sealed VALID, 3 = INVALID (retained, rejected for export), 2 = configuration refused.
No GPU is used. The sandbox faults (`--fault`) are Recorder-side only and require every output path to sit under a
`fault-sandbox/` path component.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from pathlib import Path

RC_VALID, RC_CONFIG, RC_INVALID = 0, 2, 3


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # a bad command line is a refused configuration, not an argparse exit
        from ..act.episode_recorder_process import RecorderConfigRefused
        raise RecorderConfigRefused(f"RECORDER_ARGUMENTS_INVALID: {message}")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="act_episode_recorder")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--expected-reset-epoch", type=int, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--episode-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--episode-scope", type=Path, required=True)
    parser.add_argument("--episode-inputs-manifest", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--result-file", type=Path, required=True)
    parser.add_argument("--fault", default="none")
    for name in ("batch-id", "worker-id", "point-id"):
        parser.add_argument(f"--{name}")
    for name in ("coordinator-epoch", "worker-generation", "lease-generation"):
        parser.add_argument(f"--{name}", type=int)
    for name in ("lease-issued-monotonic-s", "lease-deadline-monotonic-s"):
        parser.add_argument(f"--{name}", type=float)
    return parser


def _application_arguments(arguments):
    raw = list(sys.argv[1:] if arguments is None else arguments)
    if "--ros-args" not in raw:
        return raw
    from rclpy.utilities import remove_ros_args

    return remove_ros_args(args=["act_episode_recorder", *raw])[1:]


def _default_policy_loader(options):
    # The Recorder's bounds are the ones the freeze bound, never the live installed file.
    from ..act.frozen_runtime_inputs import load_recorder_frozen_policy

    return load_recorder_frozen_policy(options.episode_inputs_manifest)


def _default_episode_factory(options):
    # Frozen inputs, full lease, lossless writer: the shared opener only this process uses.
    from ..act.episode_open import open_recorder_episode

    return open_recorder_episode(options)


def _default_node_factory(options):
    from ..ros.episode_recorder_sources import make_recorder_node

    return make_recorder_node()


def _default_sources_factory(options, episode, policy, faults, node):
    from ..ros.episode_recorder_sources import RosRecorderSources

    return RosRecorderSources(node, episode, options, faults=faults, policy=policy)


def main(arguments: list[str] | None = None, *, episode_factory=None, sources_factory=None, node_factory=None,
         policy_loader=None, install_signal_handlers: bool = True) -> int:
    from ..act.episode_recorder_process import (RecorderConfigRefused, RecorderEngine, FaultInjector, check_outputs_absent,
                                                require_fault_sandbox)
    from ..act.teacher_event_stream import StreamIdentity

    def refuse(error) -> int:
        print(f"status=ERROR failure=RECORDER_CONFIG_REFUSED message={error}", file=sys.stderr, flush=True)
        return RC_CONFIG

    try:
        options = build_parser().parse_args(_application_arguments(arguments))
        policy = (policy_loader or _default_policy_loader)(options)
        require_fault_sandbox(options.fault, options.episode_root, options.evidence_root, options.ready_file,
                              options.result_file)
        check_outputs_absent(options.ready_file, options.result_file)
        identity = StreamIdentity(options.session_id, options.expected_reset_epoch, options.attempt_id)
        faults = FaultInjector(options.fault)
    except (RecorderConfigRefused, ValueError) as error:
        return refuse(error)

    node = None
    episode = None
    ran = False
    try:
        try:
            episode = (episode_factory or _default_episode_factory)(options)
        except (RecorderConfigRefused, ValueError, OSError) as error:
            return refuse(error)
        node = (node_factory or _default_node_factory)(options)
        sources = (sources_factory or _default_sources_factory)(options, episode, policy, faults, node)
        engine = RecorderEngine(episode=episode, sources=sources, policy=policy, identity=identity,
                                ready_file=options.ready_file, result_file=options.result_file,
                                fault=options.fault, faults=faults)
        stop = threading.Event()
        previous = {}
        if install_signal_handlers and threading.current_thread() is threading.main_thread():
            for number in (signal.SIGTERM, signal.SIGINT):
                previous[number] = signal.signal(number, lambda *_: stop.set())
        try:
            ran = True
            code = engine.run(should_stop=stop.is_set)
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)
        print(f"status={'VALID' if code == RC_VALID else 'INVALID'} rc={code} result={options.result_file}",
              flush=True)
        return code
    except RecorderConfigRefused as error:
        return refuse(error)
    finally:
        if episode is not None and not ran:
            try:
                episode.close()   # nothing was recorded: retire the writer the opener created
            except Exception as error:
                print(f"RECORDER_EPISODE_CLOSE_FAILED {error}", file=sys.stderr, flush=True)
        closer = getattr(node, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception as error:
                print(f"RECORDER_NODE_CLOSE_FAILED {error}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
