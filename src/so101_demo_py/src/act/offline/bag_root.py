"""Where a bag may live in an ACT instance, with the readback that justifies it."""

from pathlib import Path

from so101_demo.runtime.container_campaign.paths import TASK_OUTPUT_MOUNT, task_output_identity


def bag_root_decision(uri,owned_root,*,output_mount=TASK_OUTPUT_MOUNT,output_identity=task_output_identity):
    """Where a bag may live in an instance, with the readback that justifies it.

    Exactly two places: under this instance's owned root, or under the fixed output mount - and the mount only when
    it is proven to be `<owned_root>/output` itself (same device and inode, no symlink), so a path that merely has that name
    never counts. `code` is None when accepted: `CONTAINER_BAG_ROOT_MISMATCH` for a bag under neither,
    `CONTAINER_BAG_OUTPUT_NOT_INSTANCE` for a bag under the mount when the mount is not this instance's output."""
    root=Path(owned_root)
    bag=Path(uri)
    identity=output_identity(Path(output_mount),root/'output')
    decision=dict(bag=str(bag),owned_root=str(root),output_mount=str(output_mount),output_identity=identity,
        location=None,code='CONTAINER_BAG_ROOT_MISMATCH')
    if not bag.is_absolute() or '..' in bag.parts:
        return decision
    try:
        if bag.parent.resolve(strict=True)!=bag.parent:
            return decision
    except (OSError,RuntimeError):
        return decision
    if bag.is_relative_to(root):
        return dict(decision,location='owned_root',code=None)
    if bag.is_relative_to(Path(output_mount)):
        if identity.get('same') is True:
            return dict(decision,location='task_output',code=None)
        return dict(decision,code='CONTAINER_BAG_OUTPUT_NOT_INSTANCE')
    return decision
