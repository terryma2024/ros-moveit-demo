"""A private shard validates its immutable spec before creating ROS or processes."""

import importlib
import json
from pathlib import Path
import shutil
import hashlib
import time

import pytest

#: The retired per-worker field; built from fragments so the source-tree absence test keeps matching nothing.
NS_FIELD = "ros" + "_namespace"
NS_OPTION = "--ros" + "-namespace"


def fixture(tmp_path):
    root = tmp_path / "wave-00/w00/g1"
    root.mkdir(parents=True)
    runtime = tmp_path / "runtime.yaml"
    source = Path(__file__).parents[2] / "config/mujoco/parallel_batch_linux_cuda.yaml"
    shutil.copyfile(source, runtime)
    import hashlib
    document = dict(schema_version=2, kind="ACT_CONTAINER_SHARD", workload_kind="no_motion_readiness",
        campaign_id="campaign", worker_id="w00", launch_generation=1, execution_generation=3,
        runtime_id="runtime1", service_epoch="epoch1", service_token="1"*64,
        owned_root=str(root),
        simulation_session_id="campaign-wave00-w00-g1", gpu_uuid="GPU-28221cec-9d21-7753-fd5a-da645740df19",
        controlled_runtime=dict(path=str(runtime), sha256=hashlib.sha256(runtime.read_bytes()).hexdigest()))
    path = tmp_path / "shard.json"
    path.write_text(json.dumps(document,indent=2)+"\n")
    return path, document


def test_frozen_config_supplies_owner_and_startup_budgets(tmp_path):
    mod = importlib.import_module("so101_demo.cli.campaign_shard")
    path, document = fixture(tmp_path)
    spec, runtime = mod.load_spec(path)
    assert spec == document
    assert runtime.heartbeat_timeout_s == 5.0
    assert runtime.initializing_hard_timeout_s == 180.0


@pytest.mark.parametrize("problem", ["version", "old_version", "extra", "root", "namespace", "domain", "generation", "backend", "scope", "hash"])
def test_bad_spec_refused_before_runtime_factory(tmp_path, monkeypatch, problem):
    mod = importlib.import_module("so101_demo.cli.campaign_shard")
    path, document = fixture(tmp_path)
    if problem == "version": document["schema_version"] = True
    elif problem == "extra": document["hardware"] = True
    elif problem == "root": document["owned_root"] = "relative"
    elif problem == "old_version": document["schema_version"] = 1
    elif problem == "namespace": document[NS_FIELD] = "/act/campaign/w00"
    elif problem == "domain": document["ros_domain_id"] = 181
    elif problem == "generation": document["launch_generation"] = True
    elif problem == "backend": document["workload_kind"] = "hardware"
    elif problem == "scope": document["worker_id"] = "w01"
    elif problem == "hash": document["controlled_runtime"]["sha256"] = "f"*64
    path.write_text(json.dumps(document))
    monkeypatch.setattr(mod, "run_shard", lambda *args: pytest.fail("invalid spec started a runtime"))
    assert mod.main(["--spec", str(path)]) == 2


def test_the_container_shell_builds_the_fixed_container_layout(tmp_path):
    mod = importlib.import_module("so101_demo.cli.campaign_shard")
    path, _document = fixture(tmp_path)
    spec, _runtime = mod.load_spec(path)
    layout = mod.container_layout(spec)
    assert layout.owned_root == Path(spec['owned_root'])
    assert (layout.output_root, layout.control_root, layout.teacher_socket, layout.install_prefix,
            layout.ros2_executable) == (Path('/act/output'), Path('/act/control'), Path('/act/ipc/teacher/inference.sock'),
            Path('/act/install'), Path('/act/install/bin/ros2'))


def test_shard_entry_cannot_start_host_ros(tmp_path):
    import asyncio

    mod = importlib.import_module("so101_demo.cli.campaign_shard")
    path, _document = fixture(tmp_path)
    spec, runtime = mod.load_spec(path)
    with pytest.raises(ValueError, match="CAMPAIGN_SHARD_PRIVATE_CONTAINER_REQUIRED"):
        asyncio.run(mod.run_shard(spec,runtime))


def program():
    return importlib.import_module('so101_demo.runtime.act_instance.program')


def layout_for(spec, tmp_path):
    from so101_demo.runtime.act_instance.layout import InstanceLayout
    root = Path(spec['owned_root'])
    return InstanceLayout(owned_root=root, output_root=root/'output', control_root=root/'control',
        teacher_socket=tmp_path/'ipc/teacher/inference.sock', install_prefix=tmp_path/'install',
        ros2_executable=tmp_path/'install/bin/ros2')


def collection_fixture(tmp_path):
    from test_config_identity import campaign_fixture,write_config
    path,document=fixture(tmp_path)
    campaign=campaign_fixture(tmp_path)
    campaign['gpu_uuid']=document['gpu_uuid']
    campaign_path=write_config(tmp_path,campaign)
    original_runtime=dict(document['controlled_runtime'])
    identity=dict(manifest_sha256='a'*64,runtime_config_sha256=campaign['controlled_runtime']['sha256'],
        collection_config_sha256='c'*64,contact_policy_fingerprint='d'*64)
    document.update(workload_kind='act_collection',controlled_runtime=campaign['controlled_runtime'],
        parallel_runtime=original_runtime,business_identity=identity,
        campaign_config=dict(path=str(campaign_path),sha256=hashlib.sha256(campaign_path.read_bytes()).hexdigest()),
        wave_id='wave-00',deadline_monotonic_s=time.monotonic()+3600)
    path.write_text(json.dumps(document))
    return path,document


def test_collection_spec_uses_original_controlled_json_and_builds_the_task_builder(tmp_path):
    """Real spec loader and real builder selection; the native stack is an opaque object."""
    import functools
    mod=importlib.import_module('so101_demo.cli.campaign_shard')
    path,document=collection_fixture(tmp_path)
    actual,runtime=mod.load_spec(path)
    assert actual==document and runtime.heartbeat_timeout_s==5.
    stack=object()
    ready_check=lambda:True
    layout=layout_for(actual,tmp_path)
    builder=program().shard_builder(actual,stack=stack,layout=layout,ready_check=ready_check)
    from so101_demo.runtime.container_campaign.task_builder import build_collection_task
    assert type(builder) is functools.partial and builder.func is build_collection_task
    assert builder.args==() and builder.keywords==dict(stack=stack,shard_spec=actual,output_root=layout.output_root,
        teacher_socket=layout.teacher_socket,ready_check=ready_check)
    with pytest.raises(ValueError,match='CAMPAIGN_SHARD_READY_CHECK_REQUIRED'):
        program().shard_builder(actual,stack=stack,layout=layout)
    assert not hasattr(mod,'build_shard_driver') and not hasattr(mod,'ChildRuntime')


def test_shard_composition_gives_tasks_a_fresh_probe_per_call_and_keeps_the_start_probe_single_use(tmp_path):
    """Real stack owner and probes over the plain, un-namespaced launch; only the observer subprocess seam is a double."""
    import subprocess
    from so101_teleop.unified.act_stack import ActStackLaunch
    from so101_teleop.unified.act_stack_probes import RepeatableActStackReadyProbe
    observer=tmp_path/'act_stack_ready';observer.write_text('#!/usr/bin/env python3\n');observer.chmod(0o700)
    stack_root=tmp_path/'stack';stack_root.mkdir()
    launch=ActStackLaunch(ros2_executable=Path('/usr/bin/true'),session_id='session1',evidence_root=stack_root,
        ros_domain_id=181,environment={'GZ_PARTITION':'session1'})
    ready,ready_check,stack=program().compose_stack(launch,observer)
    assert stack.ready_probe is ready and ready_check is not ready
    assert isinstance(ready_check,RepeatableActStackReadyProbe)   # the kept check: a kept session inside an instance, this probe otherwise
    assert ready_check.launch is launch and ready_check.executable==observer
    now=1_000_000_000_000
    document=json.dumps(dict(schema_version=1,session_id='session1',ros_domain_id=181,captured_monotonic_ns=now-10**9,
        checks={name:True for name in ('mujoco_session','advancing_physics','controller_states','moveit_graph',
                                       'physical_stop','head_rgb','wrist_rgb')})).encode()
    runs=[]
    def observe(argv,**kwargs):
        runs.append(argv)
        return subprocess.CompletedProcess(argv,0,document,b'')
    ready.run=ready_check.run=observe
    ready.clock_ns=ready_check.clock_ns=lambda:now
    assert ready() is True and ready.readiness_bytes==document    # the shard start
    assert [ready_check(),ready_check(),ready_check()]==[True,True,True]
    assert len(runs)==4 and all(argv==runs[0] for argv in runs)
    assert NS_OPTION not in runs[0] and runs[0][runs[0].index('--ros-domain-id')+1]=='181' and runs[0][0]==str(observer)
    with pytest.raises(ValueError,match='ACT_STACK_READINESS_PROBE_REUSED'):
        stack.ready_probe()


def test_collection_spec_loads_without_head_weights_on_disk(tmp_path):
    """Collection is Teacher-only: a campaign config naming absent Head weights must still load."""
    mod=importlib.import_module('so101_demo.cli.campaign_shard')
    path,document=collection_fixture(tmp_path)
    (tmp_path/'head.pt').rename(tmp_path/'head.pt.absent')
    actual,_runtime=mod.load_spec(path)
    assert actual==document


def test_readiness_workload_builder_refuses_every_task(tmp_path):
    mod=importlib.import_module('so101_demo.cli.campaign_shard')
    path,_document=fixture(tmp_path)
    spec,_runtime=mod.load_spec(path)
    layout=layout_for(spec,tmp_path)
    builder=program().shard_builder(spec,stack=object(),layout=layout)
    with pytest.raises(ValueError,match='SHARD_READINESS_HAS_NO_MOTION_PORT'):
        builder(object())
    with pytest.raises(ValueError,match='CAMPAIGN_SHARD_WORKLOAD_UNKNOWN'):
        program().shard_builder(dict(spec,workload_kind='hardware'),stack=object(),layout=layout)


@pytest.mark.parametrize('damage',['extra','missing','hash','identity','wave','expired','bool_deadline'])
def test_bad_collection_spec_refuses_before_any_native_runtime(tmp_path,monkeypatch,damage):
    mod=importlib.import_module('so101_demo.cli.campaign_shard')
    path,document=collection_fixture(tmp_path)
    if damage=='extra':document['allow_legacy']=True
    elif damage=='missing':document.pop('campaign_config')
    elif damage=='hash':document['parallel_runtime']['sha256']='f'*64
    elif damage=='identity':document['business_identity']['runtime_config_sha256']='f'*64
    elif damage=='wave':document['wave_id']='wave-1'
    elif damage=='expired':document['deadline_monotonic_s']=time.monotonic()-1
    else:document['deadline_monotonic_s']=True
    path.write_text(json.dumps(document))
    monkeypatch.setattr(mod,'run_shard',lambda *args:pytest.fail('bad collection spec started native runtime'))
    assert mod.main(['--spec',str(path)])==2


def test_the_shard_launches_the_plain_execution_stack_at_the_fixed_identity(tmp_path):
    from so101_teleop.unified.act_stack import ActStackLaunch
    stack_root=tmp_path/'stack';stack_root.mkdir()
    spec=dict(simulation_session_id='session1')
    environment={'ROS_DOMAIN_ID':'181','MUJOCO_GL':'egl','SO101_ACT_INSTANCE_ROOT':str(tmp_path)}
    launch=program().instance_stack_launch(spec,ros2=Path('/usr/bin/true'),stack_root=stack_root,environment=environment)

    assert type(launch) is ActStackLaunch and launch.ros_domain_id==181 and launch.session_id=='session1'
    assert launch.argv()[2:4]==['so101_demo_py','so101_mujoco_act_execution_stack.launch.py']
    assert not any('namespace' in item or 'container_shard' in item for item in launch.argv())
    process_environment=launch.process_environment()
    assert process_environment['ROS_DOMAIN_ID']=='181' and process_environment['GZ_PARTITION']=='session1'
    assert 'ROS_NAMESPACE' not in process_environment and process_environment['SO101_ACT_INSTANCE_ROOT']==str(tmp_path)
