"""Binding of the scene-state, physics-chunk and RGB sources to a node (Phase A4c: moved out of `dynamic_runtime`).

The Teacher binds only the scene-state observer it needs for its release preflight; the independent Recorder process binds
the same sources plus the raw physics and camera adapters around its own episode. The code is the same, so it lives here,
away from the Teacher's execution and control modules.
"""

from __future__ import annotations

from types import SimpleNamespace

# Bounds of the data-side hazard record kept by the scene-source binding (never a control input).
_DATA_HAZARD_LIMIT = 16


class IsolatedDataNode:
    """The node as the data adapters see it: every attribute is the real node's, except that a subscription
    callback which raises latches a hazard through `on_failure` instead of unwinding the control thread's spin."""

    def __init__(self, node, on_failure):
        self._node = node
        self._on_failure = on_failure

    def __getattr__(self, name):
        return getattr(self._node, name)

    def create_subscription(self, *args, **kwargs):
        topic = str(args[1] if len(args) > 1 else kwargs.get("topic"))
        if len(args) > 2:
            callback, location = args[2], 2
        else:
            callback, location = kwargs["callback"], None
        on_failure = self._on_failure

        def isolated(*callback_args, **callback_kwargs):
            try:
                return callback(*callback_args, **callback_kwargs)
            except Exception as error:
                on_failure(f"DATA_SOURCE_CALLBACK_FAILED: {topic}: {error}")

        if location is None:
            kwargs["callback"] = isolated
        else:
            args = args[:location] + (isolated,) + args[location + 1:]
        return self._node.create_subscription(*args, **kwargs)


def bind_data_sources(node, *, session_id, reset_epoch, model_path,
                               max_age_s=0.1, expected_model=None, episode_recorder=None, scene_max_age_s=None,
                      physics_backlog_max=None, physics_lag_max_s=None):
    """Own one subscription to the existing physics producer, under its actual model identity.

    `max_age_s` is the ACT data age (physics adapter). The scene observer is also read by the Teacher's release
    preflight, so its age is `scene_max_age_s` (the Teacher state age) when given and `max_age_s` otherwise.
    """
    import mujoco
    import time
    from ..adapters.act.physics import model_sha256
    from ..adapters.act.scene_state import SceneStateObserver, RosSceneStateAdapter

    model = mujoco.MjModel.from_xml_path(str(model_path))
    identity = {"model_sha256": model_sha256(model), "nq": model.nq, "nv": model.nv,
                "mujoco_version": mujoco.__version__}
    if expected_model is not None and any(expected_model[key] != value for key, value in identity.items()):
        raise RuntimeError("DYNAMIC_SOURCE_MODEL_IDENTITY_MISMATCH")
    observer = SceneStateObserver(model_sha256=identity["model_sha256"], nq=model.nq, nv=model.nv,
                                  max_age_s=max_age_s if scene_max_age_s is None else scene_max_age_s,
                                  # Buffer capacity (about 40 s at 50 Hz) for the world drain while admission is slow.
                                  history_capacity=2048 if episode_recorder is not None else 256)
    # Bound after actual reset identity validation. The epoch starts at the reset recipe's zero
    # sim-time; release selection separately proves actual generation after normal stop.
    observer.reset(session_id, reset_epoch, source_floor_s=0.0)
    hazards = []

    def on_hazard(reason):
        # A data-source hazard is retained for the data side to judge (act_data_status INVALID). It never reaches
        # control: nothing here requests a revoke, cancel or pause, and the list is bounded.
        if len(hazards) < _DATA_HAZARD_LIMIT:
            hazards.append({"reason": str(reason)[:300], "received_monotonic_ns": time.monotonic_ns()})

    # The data adapters subscribe through a view of the node whose callbacks cannot unwind the control thread's
    # spin: a callback that raises latches a hazard instead.
    data_node = IsolatedDataNode(node, on_hazard)
    adapter = RosSceneStateAdapter(data_node, observer, on_hazard=on_hazard,
                                  subscription_depth=256 if episode_recorder is not None else 1)
    physics_adapter = None
    observation_adapter = None
    spool_process = None
    if episode_recorder is not None:
        from ..adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
        import rclpy.node
        try:
            chunks = episode_recorder.capture.audit.inputs["execution_snapshot"]["physics_chunks"]
            # Real rclpy nodes always get the dedicated receiver; only non-rclpy test doubles keep the
            # main-node subscription.
            real_node = isinstance(node, rclpy.node.Node)
            if real_node:
                # The chunk receipt runs in its own process (act/chunk_spool.py): a stall of this process's GIL
                # (a long json load, an import) cannot change a receipt; the stamp is recorded as telemetry (CP-3410).
                import tempfile
                from ..act.chunk_spool import SpoolProcess
                spool_directory = tempfile.mkdtemp(prefix="so101-chunk-spool-")
                spool_process = SpoolProcess(spool_directory, max_bytes=2 << 30,
                                               convert=(chunks["max_samples"], chunks["max_contacts"]))
                spool_process.start()
                if not spool_process.wait_ready(30.0):
                    spool_process.close()
                    raise RuntimeError("PHYSICS_RAW_SPOOLER_NOT_READY")
            physics_adapter = RosEpisodePhysicsAdapter(data_node, session_id=session_id,
                reset_epoch=reset_epoch, nq=model.nq, nv=model.nv,
                audit=episode_recorder.capture.audit, max_age_s=max_age_s,
                max_samples=chunks["max_samples"], max_contacts=chunks["max_contacts"],
                dedicated_receiver=False,
                spool=spool_process.reader() if real_node else None,
                # CP-3410: the data fails on a spool backlog or a receiver lag beyond the frozen policy, not on a late chunk
                spool_backlog_max_frames=physics_backlog_max, receiver_lag_max_s=physics_lag_max_s,
                # Buffer capacity (about 8.2 s of 2 ms steps), not a threshold: endpoint lookup window.
                history_capacity=4096)
            if real_node:
                physics_adapter.start_spool_reader()
            from ..adapters.act.ros_observation import RosObservationAdapter
            observation_adapter = RosObservationAdapter(data_node, episode_recorder.synchronizer,
                capture=episode_recorder.capture, reset_epoch=reset_epoch, on_hazard=on_hazard,
                sim_time=lambda: node.get_clock().now().nanoseconds / 1e9)
            observation_adapter.reset(session_id, source_floor_s=0.0, reset_epoch=reset_epoch)
        except Exception as error:
            # The recording sources are the data side's. A failure to build them retires whatever was built and
            # leaves the binding without them: the Teacher's own scene observer stays, the data is INVALID.
            for operation in (
                    *(() if observation_adapter is None else (observation_adapter.close,)),
                    *(() if physics_adapter is None else (physics_adapter.close,))):
                try:
                    operation()
                except Exception as cleanup_error:
                    error.add_note("Owned source construction retirement failed: " + str(cleanup_error))
            if spool_process is not None:
                spool_process.close()
            physics_adapter = observation_adapter = None
            on_hazard("DATA_SOURCE_CONSTRUCTION_FAILED: " + (str(error) or type(error).__name__)
                      + "".join(" | " + note for note in getattr(error, "__notes__", ())))

    def drain_sources():
        if physics_adapter is not None:
            return physics_adapter.drain()
        return 0

    spool_facts = {}

    def remove_spool():
        # The spool is a transient transport copy of chunks the audit already retains; it is not evidence. The spooler's
        # own numbers (chunks, bytes, longest gap between its callbacks) are kept for the Recorder's telemetry first.
        import shutil
        try:
            spool_facts.update(spool_process.reader().stats())
        except Exception:
            pass
        shutil.rmtree(spool_process.directory, ignore_errors=True)

    closed = False
    def close():
        nonlocal closed
        if not closed:
            failure = None
            try:
                for operation in (drain_sources,
                        *(() if physics_adapter is None else (physics_adapter.close,)),
                        *(() if spool_process is None else (spool_process.close, remove_spool)),
                        *(() if observation_adapter is None else (observation_adapter.close,)),
                        lambda: node.destroy_subscription(adapter.subscription)):
                    try:
                        operation()
                    except BaseException as error:
                        if failure is None:
                            failure = error
                        else:
                            failure.add_note("Further owned source retirement failed: " + str(error))
            finally:
                closed = True
            if failure is not None:
                raise failure
    return SimpleNamespace(observer=observer, adapter=adapter, hazards=hazards, model=model,
                           model_identity=identity, close=close,
                           physics_adapter=physics_adapter, observation_adapter=observation_adapter,
                           drain_sources=drain_sources, spool_stats=lambda: dict(spool_facts))
