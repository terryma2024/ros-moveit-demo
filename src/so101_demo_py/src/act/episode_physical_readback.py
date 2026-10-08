"""Independent per-row native physics, measured state and original source alignment joins."""

import math
from pathlib import Path

from .contracts import finite, integer, vector
from .qc_session import load_model
from .joints import ACT_JOINTS, ARM_JOINTS, ordered_positions
from .scene_association import (association_anchor, canonical, claim_scene_records, decode_ros, _call,
                                verify_scene_association)


def verify_physical_rows(rows, *, raw_chunks, associations, inputs, identity):
    """Recompute raw-to-row causality; this alone is neither execution nor endpoint QC."""
    import mujoco
    from moveit_msgs.msg import PlanningSceneComponents
    from moveit_msgs.srv import GetPlanningScene
    from sensor_msgs.msg import JointState
    from ..control.planning_scene.task_scene import normalized_scene_geometry
    from .execution_snapshot import verify_execution_snapshot
    from .first_episode_inputs import audit_execution_model_identity
    from .raw_physics_chunks import verify_raw_chunk

    try:
        model_identity = audit_execution_model_identity(inputs)
        if model_identity is None or not rows or not raw_chunks or not associations:
            raise ValueError("required originals absent")
        chunks = inputs["execution_snapshot"]["physics_chunks"]
        by_step, by_time, previous = {}, {}, None
        for chunk in raw_chunks:
            verify_raw_chunk(chunk, previous=previous, previous_verified=True, session_id=identity["session_id"],
                reset_epoch=identity["reset_epoch"], nq=model_identity["nq"], nv=model_identity["nv"],
                max_samples=chunks["max_samples"], max_contacts=chunks["max_contacts"])
            previous = chunk
            for sample in chunk["chunk"]["samples"]:
                step, stamp = sample["physics_step"], round(sample["simulation_time_s"] * 1e9)
                if step in by_step or stamp in by_time:
                    raise ValueError("native step/time reused")
                bound = {"sample": sample, "chunk_sequence": chunk["chunk"]["chunk_sequence"],
                         "received_monotonic_ns": chunk["received_monotonic_ns"]}
                by_step[step], by_time[stamp] = bound, sample
        scenes, calls, models = {}, {}, {}
        for document in associations:
            association_id = document["association_id"]
            if association_id in scenes:
                raise ValueError("scene association reused")
            claim_scene_records(document, calls)
            step = document["source"]["physics"]["simulation_step"]
            verify_scene_association(document, inputs=inputs, identity=identity,
                raw_steps=[] if step not in by_step else [by_step[step]["sample"]])
            scenes[association_id] = document
            root = document["execution_root"]
            if root not in models:
                snapshot = verify_execution_snapshot(root,
                    expected_sha256=inputs["execution_snapshot"]["sha256"])
                models[root] = load_model(Path(root) / snapshot["scene_path"], root=root)
        required = (PlanningSceneComponents.WORLD_OBJECT_NAMES | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
                    | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS | PlanningSceneComponents.OBJECT_COLORS)

        def at_source(stamp, grid):
            ns = round(finite(stamp, nonnegative=True) * 1e9)
            if not 0 <= grid - ns <= 100000000 or ns not in by_time:
                raise ValueError("source has no same-epoch causal native sample")
            return by_time[ns]

        def positions(model, sample, names):
            result = []
            for name in names:
                index = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
                if index < 0 or int(model.jnt_type[index]) not in (
                        int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE)):
                    raise ValueError("native measured joint mapping invalid")
                result.append(sample["model_qpos"][model.jnt_qposadr[index]])
            return result

        old_stamp, old_generation = None, None
        for row in rows:
            observation, audit = row["observation"], row["audit"]
            grid = round(finite(observation["sim_time_s"], nonnegative=True) * 1e9)
            if audit["reset_epoch"] != identity["reset_epoch"]:
                raise ValueError("row epoch mismatch")
            truth = audit["mujoco_truth"]
            if (set(truth) != {"source_kind", "sample", "chunk_sequence", "received_monotonic_ns"}
                    or truth["source_kind"] != "native_physics_step"):
                raise ValueError("native row binding absent")
            bound = by_step.get(truth["sample"]["physics_step"])
            if bound is None or canonical({key: truth[key] for key in bound}) != canonical(bound):
                raise ValueError("native row differs from original chunk")
            sample = truth["sample"]
            at_source(sample["simulation_time_s"], grid)
            contacts = [dict(contact, source_group=group)
                        for group in ("left_fingertip_contacts", "right_fingertip_contacts", "other_object_contacts")
                        for contact in sample[group]]
            if canonical(audit["contacts"]) != canonical(contacts):
                raise ValueError("contacts differ from original native sample")
            planning = audit["planning_scene"]
            bracket = planning.get("bracket")
            if set(planning) != {"query_id", "record", "association_id"} | ({"bracket"} if bracket is not None else set()):
                raise ValueError("original scene row binding absent")
            association = scenes.get(planning["association_id"])
            if association is None:
                raise ValueError("original scene association missing")
            model = models[association["execution_root"]]
            query = planning["record"]
            apply = association_anchor(association)
            geometry = canonical(association["receipt"]["geometry"])
            # CP-3449: the row's scene source may be the Teacher's successful apply that anchors the association, bounded by the
            # first read after it (the bracket, required then)
            apply_form = isinstance(query, dict) and query.get("service") == "/apply_planning_scene"
            if apply_form:
                _call(query, "/apply_planning_scene")
                if (bracket is None or association["apply"] is None or canonical(query) != canonical(apply)
                        or not isinstance(query["response"], dict) or query["response"].get("success") is not True):
                    raise ValueError("scene apply source invalid")
            else:
                _call(query, "/get_planning_scene")
                request = decode_ros(GetPlanningScene.Request, query["request"])
                response = decode_ros(GetPlanningScene.Response, query["response"])

            def causal_read(read):
                _call(read, "/get_planning_scene")
                read_request = decode_ros(GetPlanningScene.Request, read["request"])
                read_response = decode_ros(GetPlanningScene.Response, read["response"])
                return (read_request.components.components & required == required
                        and apply["response_ros_clock"]["end_monotonic_ns"] <= read["request_ros_clock"]["begin_monotonic_ns"]
                        and apply["response_ros_clock"]["sim_time_ns"] <= read["request_ros_clock"]["sim_time_ns"]
                        and canonical(normalized_scene_geometry(read_response.scene)) == geometry)

            if query["call_id"] != planning["query_id"] or (not apply_form and not causal_read(query)):
                raise ValueError("scene contents or apply-before-query causality mismatch")
            stamp_ns = query["response_ros_clock"]["sim_time_ns"]
            if bracket is None:
                if not 0 <= grid - stamp_ns <= 100000000:
                    raise ValueError("scene contents or apply-before-query causality mismatch")
            else:
                # CP-3440 B: a read older than the age rule is admitted by the next read: same association and geometry, the
                # instant lies between the two, and no scene change (an association's apply) falls between them
                if set(bracket) != {"next_query_id", "next_record"}:
                    raise ValueError("scene bracket malformed")
                following = bracket["next_record"]
                next_ns = following["response_ros_clock"]["sim_time_ns"]
                if (following["call_id"] != bracket["next_query_id"] or not causal_read(following)
                        or not stamp_ns <= grid < next_ns):
                    raise ValueError("scene bracket invalid")
                for other in scenes.values():
                    moment = association_anchor(other)["response_ros_clock"]["sim_time_ns"]
                    if stamp_ns < moment <= next_ns:
                        raise ValueError("scene changed inside the bracket")
            expected_stamps = {"cup": sample["simulation_time_s"], "contacts": sample["simulation_time_s"],
                               "planning_scene": query["response_ros_clock"]["sim_time_ns"] / 1e9}
            if canonical(audit["physical_stamps"]) != canonical(expected_stamps):
                raise ValueError("physical stamps differ from original sources")
            controller = audit["controller_state"]
            if set(controller) != {"source_stamp_ns", "generation", "positions", "received_monotonic_s", "original_message"}:
                raise ValueError("original measured state missing")
            original = decode_ros(JointState, controller["original_message"])
            integer(original.header.stamp.sec)
            integer(original.header.stamp.nanosec)
            integer(controller["source_stamp_ns"])
            integer(controller["generation"], minimum=1)
            finite(controller["received_monotonic_s"], nonnegative=True)
            stamp = original.header.stamp.sec * 1000000000 + original.header.stamp.nanosec
            if (original.header.stamp.nanosec >= 1000000000 or stamp != controller["source_stamp_ns"]
                    or len(original.name) != len(set(original.name)) or len(original.name) != len(original.position)
                    or old_stamp is not None and stamp <= old_stamp
                    or old_generation is not None and controller["generation"] <= old_generation):
                raise ValueError("original measured state clock/order invalid")
            copied = dict(zip(original.name, original.position, strict=True))
            if canonical(copied) != canonical(controller["positions"]):
                raise ValueError("measured state differs from original message")
            native = at_source(stamp / 1e9, grid)
            if list(ordered_positions(copied, ACT_JOINTS)) != positions(model, native, ACT_JOINTS):
                raise ValueError("original measured state differs from native step")
            arm = at_source(audit["source_stamps"]["arm"], grid)
            neck = at_source(audit["source_stamps"]["neck"], grid)
            yaw = positions(model, neck, ("neck_yaw_joint",))[0]
            measured = positions(model, arm, ARM_JOINTS) + [math.sin(yaw), math.cos(yaw)]
            vector(observation["state"], 8)
            if list(observation["state"]) != measured:
                raise ValueError("8D measured state differs from original native source")
            old_stamp, old_generation = stamp, controller["generation"]
        return {"rows": len(rows), "native_steps": len(by_step), "scene_associations": len(scenes)}
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
        raise ValueError("EPISODE_PHYSICAL_READBACK_INVALID") from error
