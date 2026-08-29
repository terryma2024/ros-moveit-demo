"""Fail-closed text instruction entry point for the dynamic MuJoCo pick task."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from uuid import uuid4

from ..adapters.pick_place_executor import (
    DynamicCupPickPlaceExecutor,
    DynamicRuntimeContext,
)
from ..adapters.planner.deepseek import DeepSeekPlanner
from ..adapters.planner.ollama import OllamaPlanner
from ..application.planner_chain import PlannerChain
from ..application.text_agent import AgentRequest, AgentResult, AgentStatus, TextAgent


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
    parser.add_argument("--session-id")
    parser.add_argument("--expected-reset-epoch")
    parser.add_argument("--evidence-root")
    parser.add_argument("--source-commit", default="UNRECORDED_SOURCE")
    parser.add_argument("--installed-prefix")
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
    if not source_commit or source_commit == "UNRECORDED_SOURCE":
        return None, "EXECUTION_SOURCE_COMMIT_INVALID"
    if not isinstance(options.installed_prefix, str) or not options.installed_prefix.strip():
        return None, "EXECUTION_INSTALLED_PREFIX_INVALID"
    if not Path(options.installed_prefix).is_absolute():
        return None, "EXECUTION_INSTALLED_PREFIX_INVALID"
    return (
        DynamicRuntimeContext(
            session_id=session_id,
            expected_reset_epoch=reset_epoch,
            evidence_root=evidence_root,
            source_commit=source_commit,
            installed_prefix=options.installed_prefix,
        ),
        None,
    )


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
    return True


def _compose_agent(options, context: DynamicRuntimeContext | None) -> TextAgent:
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
    executor = _PreviewExecutor() if context is None else DynamicCupPickPlaceExecutor(context)
    return TextAgent(PlannerChain(primary, fallback), executor)


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
    if not _normalize_provider_options(options):
        _write_document(_rejection(request_id, "PROVIDER_OPTIONS_INVALID"))
        return 1

    context = None
    if options.mode == "execute":
        context, reason_code = _valid_execute_context(options)
        if reason_code is not None:
            _write_document(_rejection(request_id, reason_code))
            return 1

    agent = _agent if _agent is not None else _compose_agent(options, context)
    request = AgentRequest(
        request_id=request_id,
        instruction=options.instruction,
        mode=options.mode,
        execute=options.execute,
        backend=options.backend,
    )
    try:
        result = agent.handle(request)
    except Exception:
        _write_document(_rejection(request_id, "CLI_AGENT_FAILURE"))
        return 1
    _write_document(result.to_dict())
    return _exit_code(result.status)


if __name__ == "__main__":
    raise SystemExit(main())
