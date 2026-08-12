"""Backend-neutral staged-approach helpers."""


def maximum_joint_error(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    if len(first) != len(second):
        raise ValueError("joint vectors must have equal length")
    return max((abs(left - right) for left, right in zip(first, second, strict=True)), default=0.0)
