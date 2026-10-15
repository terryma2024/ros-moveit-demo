"""The processor program: spec, container shell and the one-way task flow through the shared executor."""

import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import time

import pytest

from so101_demo.runtime.act_processor import processing, program
from so101_demo.runtime.act_processor.layout import ProcessorLayout
from so101_demo.runtime.act_processor.spec import load_processor_spec, processor_launch_id
from so101_demo.runtime.container_campaign.task_executor import ContainerTaskExecutor
from so101_demo.runtime.container_campaign.task_results import read_task_result

from test_processor_processing import FakeRunner, Fixture, fake_grader


def spec_fixture(tmp_path, **override):
    processing_root = tmp_path / "run" / "processing"
    owned = processing_root / "p03" / "g2"
    owned.mkdir(parents=True)
    runtime = tmp_path / "runtime.yaml"
    shutil.copyfile(Path(__file__).parents[3] / "config/mujoco/parallel_batch_linux_cuda.yaml", runtime)
    document = dict(schema_version=1, kind="ACT_CONTAINER_PROCESSOR", campaign_id="campaign", processor_id="p03",
                    launch_generation=2, execution_generation=3, runtime_id="runtime1", service_epoch="epoch1",
                    service_token="1" * 64, owned_root=str(owned), processing_root=str(processing_root),
                    parallel_runtime=dict(path=str(runtime), sha256=hashlib.sha256(runtime.read_bytes()).hexdigest()),
                    deadline_monotonic_s=time.monotonic() + 3600)
    document.update(override)
    path = tmp_path / "processor.json"
    path.write_text(json.dumps(document))
    return path, document


def test_spec_loads_and_names_the_launch(tmp_path):
    path, document = spec_fixture(tmp_path)
    spec, runtime = load_processor_spec(path)
    assert spec == document and runtime.heartbeat_timeout_s == 5.0
    assert processor_launch_id(spec) == "processing-p03-g2"


@pytest.mark.parametrize("override", [dict(processor_id="w03"), dict(processor_id="p04"), dict(launch_generation=3),
                                      dict(kind="ACT_CONTAINER_SHARD"), dict(extra=1), dict(service_token="x"),
                                      dict(schema_version=True), dict(deadline_monotonic_s=1.0), dict(campaign_id="a b")])
def test_bad_spec_is_refused(tmp_path, override):
    path, _ = spec_fixture(tmp_path, **override)
    with pytest.raises(ValueError, match="CAMPAIGN_PROCESSOR_SPEC_INVALID"):
        load_processor_spec(path)


def test_shell_refuses_a_bad_spec_before_any_runtime(tmp_path, monkeypatch):
    from so101_demo.cli import campaign_processor
    path, _ = spec_fixture(tmp_path, processor_id="w03")
    monkeypatch.setattr(campaign_processor, "run_in_container", lambda *args: pytest.fail("started a runtime"))
    assert campaign_processor.main(["--spec", str(path)]) == 2


def test_shell_refuses_to_run_outside_a_private_container(tmp_path):
    from so101_demo.cli import campaign_processor
    path, _ = spec_fixture(tmp_path)
    assert campaign_processor.main(["--spec", str(path)]) == 1


def test_container_layout_is_derived_from_the_spec(tmp_path):
    from so101_demo.cli import campaign_processor
    path, _ = spec_fixture(tmp_path)
    spec, _ = load_processor_spec(path)
    layout = campaign_processor.container_layout(spec)
    assert layout.owned_root == Path(spec["owned_root"]) and layout.output_root == layout.owned_root / "output"
    assert layout.control_root == Path("/act/control") and layout.python == Path("/act/venv/bin/python")


def test_layout_refuses_relative_and_aliased_paths(tmp_path):
    with pytest.raises(ValueError):
        ProcessorLayout(owned_root="rel", output_root="/a/o", control_root="/a/c", python="/p")
    with pytest.raises(ValueError):
        ProcessorLayout(owned_root="/a", output_root="/a", control_root="/a/c", python="/p")


def test_assign_poll_and_result_flow_through_the_shared_executor(tmp_path):
    fixture = Fixture(tmp_path)
    layout = ProcessorLayout(owned_root=fixture.owned, output_root=fixture.owned / "output", control_root=fixture.owned / "control",
                             python="/act/venv/bin/python")
    layout.output_root.mkdir()
    spec = dict(processing_root=str(fixture.processing), processor_id="p00", launch_generation=1,
                deadline_monotonic_s=time.monotonic() + 3600)
    runner = FakeRunner(0)
    build = program.processor_builder(spec, layout=layout, runner_factory=lambda: runner, grader=fake_grader,
                                      memo_check=lambda **kwargs: True)

    async def flow():
        executor = ContainerTaskExecutor(instance_id=processor_launch_id(dict(processor_id="p00", launch_generation=1)),
            builder=build, retirement=program.NoRosRetirement(), output_root=layout.output_root, owner_timeout_s=30,
            stop_timeout_s=5, retire_timeout_s=5, ready=True)
        task = fixture.task()
        accepted = await executor.assign_task(task)
        assert accepted.state == "ACCEPTED"
        for _ in range(400):
            status = await executor.get_status(task.task_id)
            if status.task.state in ("SUCCEEDED", "FAILED"):
                break
            await asyncio.sleep(0.01)
        assert status.task.state == "SUCCEEDED"
        stopped = await executor.terminate("test over")
        assert stopped.state == "STOPPING"
        await executor.wait_stopped()
        assert executor.cleanup_confirmed is True
        return task
    task = asyncio.run(flow())
    document = read_task_result(layout.output_root, task.task_id)
    assert document["result"]["outcome"] == "VALID" and document["result"]["kind"] == "ACT_PROCESSING_TASK_RESULT"
    assert (fixture.output_dir / "processed-result.json").is_file()


def test_a_task_past_the_spec_deadline_is_refused_by_the_builder(tmp_path):
    fixture = Fixture(tmp_path)
    layout = ProcessorLayout(owned_root=fixture.owned, output_root=fixture.owned / "output", control_root=fixture.owned / "control",
                             python="/p")
    layout.output_root.mkdir()
    spec = dict(processing_root=str(fixture.processing), processor_id="p00", launch_generation=1,
                deadline_monotonic_s=time.monotonic() + 10)
    with pytest.raises(ValueError, match="PROCESSING_TASK_DEADLINE_INVALID"):
        program.processor_builder(spec, layout=layout)(fixture.task())


def test_the_processor_entrypoint_is_installed():
    setup = (Path(__file__).parents[3] / "setup.py").read_text()
    assert '"campaign_processor = so101_demo.cli.campaign_processor:main"' in setup
