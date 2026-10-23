"""The native shell of the ACT processor program: checks the native-only facts, builds the layout, runs it.

Everything a processor does lives in `so101_demo.runtime.act_processor.program`, the same program the container shell
(`campaign_processor`) runs. This shell only knows what is true for a native processor started by `NativeProcessorOwner`: the
process leads a session and process group of its own, the Host set the instance marker naming this owned root, the code it runs is
the installed prefix the Host named, and its directories are the owned root's own (`output`, `control`). The interpreter that runs
`act_offline_episode` is the one running this shell.
"""

import argparse
import asyncio
import os
from pathlib import Path
import sys

from so101_demo.runtime.act_instance.identity import INSTANCE_OUTPUT_ENV, INSTANCE_ROOT_ENV
from so101_demo.runtime.act_processor.layout import ProcessorLayout
from so101_demo.runtime.act_processor.program import run_processor
from so101_demo.runtime.act_processor.spec import load_processor_spec


def native_layout(spec):
    """The layout of a native processor: its owned root's own directories and the interpreter running this shell."""
    root = Path(spec["owned_root"])
    return ProcessorLayout(owned_root=root, output_root=root / "output", control_root=root / "control",
                           python=Path(sys.executable))


def running_installed_code(install_prefix):
    """Whether the imported `so101_demo` is the installed package under the Host-named prefix, not a source tree."""
    import so101_demo

    return Path(os.path.abspath(so101_demo.__file__)).is_relative_to(Path(install_prefix))


def check_native_process(spec, install_prefix):
    """The facts a native processor must have before it runs the program; the program checks the rest."""
    root = spec["owned_root"]
    if os.getpid() != os.getpgrp() or os.getpid() != os.getsid(0):
        raise ValueError("CAMPAIGN_NATIVE_GROUP_REQUIRED")
    if os.environ.get(INSTANCE_ROOT_ENV) != root or os.environ.get(INSTANCE_OUTPUT_ENV) != root + "/output":
        raise ValueError("CAMPAIGN_NATIVE_ENVIRONMENT_DRIFT")
    if not Path(install_prefix).is_absolute() or not running_installed_code(install_prefix):
        raise ValueError("CAMPAIGN_NATIVE_CODE_NOT_INSTALLED")


async def run_native(spec, runtime_config, install_prefix):
    check_native_process(spec, install_prefix)
    return await run_processor(spec, runtime_config, native_layout(spec))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--install-prefix", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        spec, runtime = load_processor_spec(args.spec)
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    try:
        return asyncio.run(run_native(spec, runtime, args.install_prefix))
    except (OSError, ValueError, RuntimeError) as error:
        print(f"CAMPAIGN_NATIVE_PROCESSOR_FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
