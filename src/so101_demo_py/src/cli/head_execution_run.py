"""The formal stage-one execution entry: one verified input document, one run.

Usage (through the installed calibration CLI):

    so101_head_search_calibration run --execution-inputs /abs/execution-inputs.json

This entry owns the whole contract of a development run: it parses the single
closed input document, refuses anything else with the documented return codes,
resolves the one production resource provider before it touches the run root,
opens the single composition and lets the provider bind the stack, the model and
the ROS context exactly once. The provider is resolved before any filesystem
effect, so an absent or uninstalled provider leaves no half-created run.

Return codes: 0 for a completed run, 1 for a business/safety/runtime failure
(sealed as a failure), 2 for an input, environment or ownership refusal.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

from so101_demo.act.head_execution_inputs import HeadExecutionInputs
from so101_demo.act.head_execution_inputs import HeadExecutionInputsRefused
from so101_demo.adapters.act.head_execution_composition import HeadExecutionComposition
from so101_demo.adapters.act.head_execution_composition import HeadExecutionCompositionRefused
from so101_demo.adapters.act.head_execution_composition import run_head_execution

#: the one installed module that may construct the stack, the model and the node
PROVIDER_MODULE = 'so101_demo.adapters.act.head_execution_provider'
PROVIDER_ATTRIBUTE = 'provide'

PROVIDER_REQUIRED = 'EXECUTION_PROVIDER_REQUIRED'
PROVIDER_ABSENT = 'EXECUTION_PROVIDER_ABSENT'
RUN_FAILED = 'EXECUTION_RUN_FAILED'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='so101_head_search_calibration run --execution-inputs',
        description='Run one file-protocol stage-one development run from its sealed input document',
    )
    parser.add_argument('--execution-inputs', required=True,
                        help='absolute path of the closed execution-input document')
    parser.add_argument('--print-readback', action='store_true',
                        help='print the opened composition readback as JSON')
    return parser


def resolve_provider(provider=None):
    """Resolve the installed resource provider, or None when it is not installed."""

    if provider is not None:
        return provider
    try:
        module = importlib.import_module(PROVIDER_MODULE)
    except ImportError:
        return None
    candidate = getattr(module, PROVIDER_ATTRIBUTE, None)
    return candidate if callable(candidate) else None


def main(argv=None, *, provider=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        parsed = build_parser().parse_args(arguments)
    except SystemExit as exit_request:
        return 2 if exit_request.code else 0
    try:
        inputs = HeadExecutionInputs.parse(Path(parsed.execution_inputs))
    except HeadExecutionInputsRefused as refusal:
        print(f'{refusal.code}: {refusal.detail}', file=sys.stderr)
        return 2
    resolved = resolve_provider(provider)
    if resolved is None:
        print(f'{PROVIDER_ABSENT}: the installed resource provider '
              f'{PROVIDER_MODULE}.{PROVIDER_ATTRIBUTE} is not available; no run root was created',
              file=sys.stderr)
        return 2
    try:
        composition = run_head_execution(inputs)
    except HeadExecutionCompositionRefused as refusal:
        print(f'{refusal.code}: {refusal.detail}', file=sys.stderr)
        return 2
    code = _execute(composition, resolved, inputs)
    if parsed.print_readback:
        print(json.dumps(composition.readback(), sort_keys=True))
    return code


def _execute(composition, resolved, inputs) -> int:
    """Run the provider through the open composition and seal the run exactly once."""

    try:
        outcome = resolved(composition, inputs)
    except Exception as error:  # a provider failure is a sealed business failure
        return _seal_failure(composition, f'{type(error).__name__}: {error}'[:256])
    business = outcome
    if type(business) is not int or business not in (0, 1):
        return _seal_failure(composition, 'the provider returned an invalid outcome')
    try:
        composition.seal({'execution': 'SUCCEEDED' if business == 0 else 'FAILED',
                          'business_return_code': business})
    except HeadExecutionCompositionRefused as refusal:
        print(f'{refusal.code}: {refusal.detail}', file=sys.stderr)
        return 1
    return business


def _seal_failure(composition, reason) -> int:
    """Seal a failure completion; an incomplete composition records it and is refused."""

    try:
        composition.seal({'execution': 'FAILED', 'business_return_code': 1, 'failure': reason})
    except HeadExecutionCompositionRefused as refusal:
        print(f'{refusal.code}: {refusal.detail}', file=sys.stderr)
    except Exception as error:
        print(f'{RUN_FAILED}: {reason}; the run could not be sealed ({type(error).__name__})',
              file=sys.stderr)
        return 1
    print(f'{RUN_FAILED}: {reason}', file=sys.stderr)
    import traceback as _tb
    _tb.print_exc()
    return 1


if __name__ == '__main__':  # pragma: no cover - module entry
    raise SystemExit(main())
