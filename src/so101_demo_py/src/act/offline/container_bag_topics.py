"""An immutable scoped-channel map tied to the original native shard readiness.

Only channel addresses change. Payloads, timestamps, counts and existing offline
logical source contracts remain unchanged; foreign channels are never dropped.
"""

from pathlib import Path
import os

from so101_demo.act.parallel_collection_contracts import read_document
from so101_demo.runtime.container_campaign.paths import TASK_OUTPUT_MOUNT,_path,task_output_identity
from so101_demo.runtime.container_campaign.ros_namespace import validate_container_namespace,qualified_name
from so101_demo.runtime.inference.config import calibration_runtime_hash,validate_file_ref
from so101_demo.runtime.parallel_ipc.frames import canonical_json


_FIELDS={'schema_version','kind','owned_root','ros_namespace','runtime_ready','topics'}


def topic_map_path(uri):
    bag=Path(uri)
    return bag.parent/(bag.name+'-topic-map.json')


def bag_root_decision(uri,owned_root,*,output_mount=TASK_OUTPUT_MOUNT,output_identity=task_output_identity):
    """Where a scoped bag may live in a container, with the readback that justifies it.

    Exactly two places: under this instance's native owned root, or under the fixed output mount - and the mount only when
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


def _validate(document,uri,*,output_mount=TASK_OUTPUT_MOUNT,output_identity=task_output_identity):
    if (type(document) is not dict or set(document)!=_FIELDS
            or type(document['schema_version']) is not int or document['schema_version']!=1
            or document['kind']!='ACT_CONTAINER_BAG_TOPICS'):
        raise ValueError('CONTAINER_BAG_TOPIC_MAP_INVALID')
    root=_path(document['owned_root'],directory=True)
    bag=Path(uri)
    decision=bag_root_decision(bag,root,output_mount=output_mount,output_identity=output_identity)
    if decision['code'] is not None:
        raise ValueError(decision['code'])
    namespace=validate_container_namespace(document['ros_namespace'])
    ready_ref=document['runtime_ready']
    if ready_ref['path']!=str(root/'runtime-ready.json'):
        raise ValueError('CONTAINER_BAG_READINESS_MISMATCH')
    ready=read_document(validate_file_ref(ready_ref))
    if (ready.get('kind')!='ACT_SHARD_RUNTIME_READY' or type(ready.get('schema_version')) is not int
            or ready['schema_version']!=1 or ready.get('ros_namespace')!=namespace
            or type(ready.get('generation')) is not int or root.name!='g'+str(ready['generation'])):
        raise ValueError('CONTAINER_BAG_READINESS_MISMATCH')
    validate_file_ref(ready_ref)
    topics=document['topics']
    if (type(topics) is not dict or not topics or any(
            qualified_name(namespace,logical)!=physical for logical,physical in topics.items())
            or len(set(topics.values()))!=len(topics)):
        raise ValueError('CONTAINER_BAG_TOPIC_MAP_INVALID')
    return dict(topics)


def write_topic_map(uri,*,owned_root,namespace,topics,output_mount=TASK_OUTPUT_MOUNT,output_identity=task_output_identity):
    root=Path(owned_root)
    document=dict(schema_version=1,kind='ACT_CONTAINER_BAG_TOPICS',owned_root=str(root),
        ros_namespace=namespace,runtime_ready=dict(path=str(root/'runtime-ready.json'),
            sha256=calibration_runtime_hash(root/'runtime-ready.json')),
        topics={topic:qualified_name(namespace,topic) for topic in topics})
    mapping=_validate(document,uri,output_mount=output_mount,output_identity=output_identity)
    target=topic_map_path(uri)
    descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'wb') as stream:
        stream.write(canonical_json(document)+b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    directory=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(directory)
    finally:os.close(directory)
    return mapping


def read_topic_map(uri,*,output_mount=TASK_OUTPUT_MOUNT,output_identity=task_output_identity):
    path=topic_map_path(uri)
    try:path.lstat()
    except FileNotFoundError:return {}
    return _validate(read_document(path),uri,output_mount=output_mount,output_identity=output_identity)


def logical_channel_map(uri,physical_names):
    mapping=read_topic_map(uri)
    if not mapping:return {name:name for name in physical_names}
    reverse={physical:logical for logical,physical in mapping.items()}
    if any(name not in reverse for name in physical_names):
        raise ValueError('CONTAINER_BAG_FOREIGN_CHANNEL')
    return {name:reverse[name] for name in physical_names}
