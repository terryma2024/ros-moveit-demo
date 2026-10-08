"""Original controller publications beside the exact projected label values."""

from .contracts import integer
from .qc_session import Identity, session_memo
from .scene_association import canonical, decode_ros


@session_memo(lambda frame, kind: (Identity(frame), kind), copy_result=False)
def verify_original_frame(frame, kind):
    from control_msgs.msg import JointTrajectoryControllerState
    from .joints import ARM_JOINTS

    try:
        original = decode_ros(JointTrajectoryControllerState, frame["original_message"])
        integer(original.header.stamp.sec)
        integer(original.header.stamp.nanosec)
        stamp = original.header.stamp.sec * 1000000000 + original.header.stamp.nanosec
        names = {"arm": ARM_JOINTS[:5], "gripper": ARM_JOINTS[5:]}[kind]
        if (original.header.stamp.nanosec >= 1000000000 or stamp != frame["sim_stamp_ns"]
                or tuple(original.joint_names) != names or list(original.joint_names) != frame["joint_names"]
                or canonical(list(original.reference.positions)) != canonical(frame["published_positions"])
                or canonical(list(original.reference.velocities)) != canonical(frame["published_velocities"])
                or frame["evaluation"]["basis"] != "published"):
            raise ValueError("original reference mismatch")
        return True
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        raise ValueError("EPISODE_REFERENCE_READBACK_INVALID") from error


def verify_original_references(references):
    from .episode_audit import _REFERENCE_FIELDS, _REFERENCE_FRAME_FIELDS, _reference_frames_ok
    try:
        if not references:
            raise ValueError("original references absent")
        history = {}
        for index, record in enumerate(references):
            if (set(record) != _REFERENCE_FIELDS | _REFERENCE_FRAME_FIELDS
                    or record["source"] != "CONTROLLER_REFERENCE" or record["accepted"] is not True
                    or type(record["sequence"]) is not int or record["sequence"] != index + 1):
                raise ValueError("reference stream invalid")
            _reference_frames_ok(record, history=history)
            for kind, frame in record["frames"].items():
                verify_original_frame(frame, kind)
        return len(references)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        raise ValueError("EPISODE_REFERENCE_READBACK_INVALID") from error
