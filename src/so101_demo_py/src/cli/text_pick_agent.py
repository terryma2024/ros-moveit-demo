"""Fail-closed text instruction entry point for the dynamic MuJoCo pick task."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from ..adapters.pick_place_executor import (
    DynamicCupPickPlaceExecutor,
    DynamicRuntimeContext,
)
from ..adapters.planner.deepseek import (
    DeepSeekPlanner,
    is_production_deepseek_configuration,
)
from ..adapters.planner.ollama import (
    OllamaPlanner,
    is_production_ollama_configuration,
)
from ..application.planner_chain import PlannerChain
from ..application.text_agent import AgentRequest, AgentStatus, TextAgent
from ..application.task_dispatch import TaskDispatcher
from ..profiling.model import ProfilingConfig, ProfilingMode
from ..profiling.session import SemanticProfiler, build_profiler
from ..profiling.wrappers import (
    profile_dispatcher,
    profile_executor,
    profile_planner,
)


def new_request_id() -> str:
    return str(uuid4())


class _PreviewExecutor:
    """A composition placeholder that cannot invoke a live runtime."""

    def dispatch(self, _request):
        raise AssertionError("preview execution is forbidden")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="text_pick_agent")
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--request-id")
    parser.add_argument("--mode", default="preview")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirmation-digest")
    parser.add_argument("--skip-confirmation", action="store_true")
    parser.add_argument("--backend", default="mujoco")
    parser.add_argument("--deepseek-model", default="deepseek-v4-flash")
    parser.add_argument(
        "--deepseek-endpoint", default="https://api.deepseek.com/chat/completions"
    )
    parser.add_argument("--deepseek-timeout-s", type=float, default=8.0)
    parser.add_argument("--ollama-model", default="qwen3.5:4b")
    parser.add_argument(
        "--ollama-endpoint", default="http://127.0.0.1:11434/api/chat"
    )
    parser.add_argument("--ollama-timeout-s", type=float, default=12.0)
    parser.add_argument("--cup-pose-timeout-s", type=float, default=30.0)
    parser.add_argument("--session-id")
    parser.add_argument("--expected-reset-epoch")
    parser.add_argument("--evidence-root")
    parser.add_argument("--source-commit", default="UNRECORDED_SOURCE")
    parser.add_argument("--installed-prefix")
    parser.add_argument(
        "--profiling",
        choices=[mode.value for mode in ProfilingMode],
        default=ProfilingMode.OFF.value,
    )
    parser.add_argument("--profiling-output-root")
    parser.add_argument("--profiling-session-id")
    return parser


def _rejection(request_id: str, reason_code: str) -> dict[str, object]:
    return {
        "request_id": request_id,
        "status": AgentStatus.DISPATCH_REJECTED.value,
        "reason_code": reason_code,
        "dispatch": False,
        "state_trace": [AgentStatus.DISPATCH_REJECTED.value],
    }


def _write_document(document: dict[str, object]) -> None:
    print(json.dumps(document, ensure_ascii=False, sort_keys=True), flush=True)


def _valid_execute_context(options) -> tuple[DynamicRuntimeContext | None, str | None]:
    if not isinstance(options.session_id, str):
        return None, "EXECUTION_SESSION_ID_REQUIRED"
    session_id = options.session_id.strip()
    if not session_id:
        return None, "EXECUTION_SESSION_ID_REQUIRED"
    try:
        reset_epoch = int(options.expected_reset_epoch)
    except (TypeError, ValueError):
        return None, "EXECUTION_RESET_EPOCH_INVALID"
    if reset_epoch < 0:
        return None, "EXECUTION_RESET_EPOCH_INVALID"
    if not isinstance(options.evidence_root, str):
        return None, "EXECUTION_EVIDENCE_ROOT_INVALID"
    evidence_root = Path(options.evidence_root)
    if not evidence_root.is_absolute():
        return None, "EXECUTION_EVIDENCE_ROOT_INVALID"
    if not isinstance(options.source_commit, str):
        return None, "EXECUTION_SOURCE_COMMIT_INVALID"
    source_commit = options.source_commit.strip()
    if re.fullmatch(r"[0-9a-fA-F]{40}", source_commit) is None:
        return None, "EXECUTION_SOURCE_COMMIT_INVALID"
    if not isinstance(options.installed_prefix, str) or not options.installed_prefix.strip():
        return None, "EXECUTION_INSTALLED_PREFIX_INVALID"
    installed_prefix = options.installed_prefix.strip()
    if not Path(installed_prefix).is_absolute():
        return None, "EXECUTION_INSTALLED_PREFIX_INVALID"
    from ..runtime.provenance import (
        ExecutionProvenanceError,
        verify_execution_provenance,
    )

    try:
        execution_provenance = verify_execution_provenance(
            declared_source_commit=source_commit,
            declared_installed_prefix=installed_prefix,
            session_id=session_id,
            expected_reset_epoch=reset_epoch,
            evidence_root=evidence_root,
        )
    except ExecutionProvenanceError as error:
        return None, error.code
    return (
        DynamicRuntimeContext(
            session_id=session_id,
            expected_reset_epoch=reset_epoch,
            evidence_root=Path(execution_provenance.evidence_root),
            source_commit=execution_provenance.source_commit,
            installed_prefix=execution_provenance.installed_prefix,
            execution_provenance=execution_provenance,
        ),
        None,
    )


def _persist_execution_provenance(
    context: DynamicRuntimeContext,
    request_id: str,
    confirmation_mode: str,
    *,
    confirmation_validated: bool,
) -> None:
    directory = context.evidence_root / "text-agent-provenance"
    directory.mkdir(parents=True, exist_ok=True)
    filename = hashlib.sha256(request_id.encode("utf-8")).hexdigest() + ".json"
    destination = directory / filename
    document = {
        "request_id": request_id,
        "confirmation_mode": confirmation_mode,
        "confirmation_validated": confirmation_validated,
        "execution_provenance": context.execution_provenance.to_dict(),
    }
    encoded = (
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=directory,
            prefix=".provenance-",
            delete=False,
        ) as stream:
            temporary_path = stream.name
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                Path(temporary_path).unlink()
            except OSError:
                pass


def _normalize_provider_options(options) -> bool:
    string_names = (
        "deepseek_model",
        "deepseek_endpoint",
        "ollama_model",
        "ollama_endpoint",
    )
    for name in string_names:
        value = getattr(options, name)
        if not isinstance(value, str):
            return False
        normalized = value.strip()
        if not normalized:
            return False
        setattr(options, name, normalized)
    for name in ("deepseek_timeout_s", "ollama_timeout_s"):
        value = getattr(options, name)
        if type(value) is not float or not math.isfinite(value) or value <= 0:
            return False
    return is_production_deepseek_configuration(
        options.deepseek_model,
        options.deepseek_endpoint,
        options.deepseek_timeout_s,
    ) and is_production_ollama_configuration(
        options.ollama_model,
        options.ollama_endpoint,
        options.ollama_timeout_s,
    )


def _valid_cup_pose_timeout(options) -> bool:
    value = options.cup_pose_timeout_s
    return type(value) is float and math.isfinite(value) and value > 0.0


def _compose_agent(
    options,
    context: DynamicRuntimeContext | None,
    profiler: SemanticProfiler | None = None,
) -> TextAgent:
    primary = DeepSeekPlanner(
        os.environ.get("DEEPSEEK_API_KEY", ""),
        model=options.deepseek_model,
        endpoint=options.deepseek_endpoint,
        timeout_s=options.deepseek_timeout_s,
    )
    fallback = OllamaPlanner(
        model=options.ollama_model,
        endpoint=options.ollama_endpoint,
        timeout_s=options.ollama_timeout_s,
    )
    planner = PlannerChain(primary, fallback)
    executor = (
        _PreviewExecutor()
        if context is None
        else DynamicCupPickPlaceExecutor(
            context,
            cup_pose_timeout_s=options.cup_pose_timeout_s,
        )
    )
    if profiler is None:
        return TextAgent(planner, executor)
    planner = profile_planner(
        planner,
        profiler,
        provider="deepseek+ollama",
        model=f"{options.deepseek_model}|{options.ollama_model}",
    )
    executor = profile_executor(executor, profiler)
    dispatcher = profile_dispatcher(TaskDispatcher(), profiler)
    return TextAgent(
        planner,
        executor,
        dispatcher=dispatcher,
        profiler=profiler,
    )


def _build_semantic_profiler(
    options,
    *,
    request_id: str,
    process_role: str = "text-agent",
) -> SemanticProfiler | None:
    mode = ProfilingMode.parse(options.profiling)
    if mode is ProfilingMode.OFF:
        return None
    if not isinstance(options.profiling_output_root, str):
        raise ValueError("enabled profiling requires --profiling-output-root")
    output_root = Path(options.profiling_output_root)
    if not output_root.is_absolute():
        raise ValueError("profiling output root must be absolute")
    if (
        not isinstance(options.profiling_session_id, str)
        or not options.profiling_session_id.strip()
    ):
        raise ValueError("enabled profiling requires --profiling-session-id")
    source_commit = (
        options.source_commit.strip().lower()
        if isinstance(options.source_commit, str)
        and re.fullmatch(r"[0-9a-fA-F]{40}", options.source_commit.strip())
        else None
    )
    installed_prefix = (
        options.installed_prefix.strip()
        if isinstance(options.installed_prefix, str)
        and Path(options.installed_prefix.strip()).is_absolute()
        else None
    )
    return build_profiler(
        ProfilingConfig(
            mode=mode,
            output_root=output_root,
            session_id=options.profiling_session_id.strip(),
            process_role=process_role,
            request_id=request_id,
            source_commit=source_commit,
            installed_prefix=installed_prefix,
        )
    )


def _exit_code(status: AgentStatus) -> int:
    return int(status not in {AgentStatus.DISPATCH_PREVIEW, AgentStatus.RUNTIME_COMPLETED})


def main(arguments: list[str] | None = None, *, _agent: TextAgent | None = None) -> int:
    options = build_parser().parse_args(arguments)
    request_id = options.request_id if options.request_id is not None else new_request_id()

    if options.backend != "mujoco":
        _write_document(_rejection(request_id, "BACKEND_NOT_QUALIFIED"))
        return 1
    if (options.mode == "execute") != options.execute:
        _write_document(_rejection(request_id, "PARTIAL_EXECUTE_AUTHORIZATION"))
        return 1
    if options.mode not in {"preview", "execute"}:
        _write_document(_rejection(request_id, "MODE_INVALID"))
        return 1
    if options.skip_confirmation and options.mode != "execute":
        _write_document(
            _rejection(request_id, "CONFIRMATION_BYPASS_REQUIRES_EXECUTE")
        )
        return 1
    if options.skip_confirmation and options.confirmation_digest is not None:
        _write_document(_rejection(request_id, "CONFIRMATION_MODE_CONFLICT"))
        return 1
    if not _valid_cup_pose_timeout(options):
        _write_document(_rejection(request_id, "CUP_POSE_TIMEOUT_INVALID"))
        return 1
    if not _normalize_provider_options(options):
        _write_document(_rejection(request_id, "PROVIDER_OPTIONS_INVALID"))
        return 1

    context = None
    confirmation_mode = None
    if options.mode == "execute":
        confirmation_mode = "skipped" if options.skip_confirmation else "digest"
        context, reason_code = _valid_execute_context(options)
        if reason_code is not None:
            _write_document(_rejection(request_id, reason_code))
            return 1
        try:
            _persist_execution_provenance(
                context,
                request_id,
                confirmation_mode,
                confirmation_validated=False,
            )
        except (OSError, TypeError, ValueError):
            _write_document(_rejection(request_id, "EXECUTION_PROVENANCE_PERSIST_FAILED"))
            return 1

    profiler = None
    runtime_profiler = None
    try:
        profiler = _build_semantic_profiler(options, request_id=request_id)
        if context is not None and profiler is not None:
            runtime_profiler = _build_semantic_profiler(
                options,
                request_id=request_id,
                process_role="dynamic-runtime",
            )
            context = replace(context, profiler=runtime_profiler)
    except OSError:
        if profiler is not None:
            profiler.close()
        profiler = None
        runtime_profiler = None
    except (TypeError, ValueError):
        if profiler is not None:
            profiler.close()
        _write_document(_rejection(request_id, "PROFILING_CONFIGURATION_INVALID"))
        return 1
    try:
        agent = (
            _agent
            if _agent is not None
            else _compose_agent(options, context, profiler=profiler)
        )
        request = AgentRequest(
            request_id=request_id,
            instruction=options.instruction,
            mode=options.mode,
            execute=options.execute,
            backend=options.backend,
            confirmation_digest=options.confirmation_digest,
            skip_confirmation=options.skip_confirmation,
            execution_provenance=(
                context.execution_provenance if context is not None else None
            ),
        )
        try:
            result = agent.handle(request)
        except Exception:
            _write_document(_rejection(request_id, "CLI_AGENT_FAILURE"))
            return 1
        document = result.to_dict()
        provenance_finalize_failed = False
        if context is not None:
            document["execution_provenance"] = context.execution_provenance.to_dict()
            if result.confirmation_mode is not None:
                try:
                    _persist_execution_provenance(
                        context,
                        request_id,
                        result.confirmation_mode,
                        confirmation_validated=True,
                    )
                except (OSError, TypeError, ValueError):
                    document["reason_code"] = "EXECUTION_PROVENANCE_FINALIZE_FAILED"
                    provenance_finalize_failed = True
        _write_document(document)
        if provenance_finalize_failed:
            return 1
        return _exit_code(result.status)
    finally:
        if runtime_profiler is not None:
            runtime_profiler.close()
        if profiler is not None:
            profiler.close()


if __name__ == "__main__":
    raise SystemExit(main())
