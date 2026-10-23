"""The container shell of the ACT processor program: checks the container-only facts, builds the layout, runs it.

Everything a processor does lives in `so101_demo.runtime.act_processor.program`. This shell only knows what is true inside a
processor container: it is pid 1 and runs the image's interpreter. Its directories are bind mounts at the Host's own paths (the
owned root, `<owned_root>/output` and `<owned_root>/control`), so the layout is derived from the spec.
"""

import argparse
import asyncio
import os
from pathlib import Path
import sys

from so101_demo.runtime.act_processor.layout import ProcessorLayout
from so101_demo.runtime.act_processor.program import run_processor
from so101_demo.runtime.act_processor.spec import load_processor_spec
from so101_demo.runtime.container_campaign.paths import CONTAINER_CONTROL_ROOT, CONTAINER_INTERPRETER


def container_layout(spec):
    """The fixed layout of a processor container: the mounts of `build_role_mounts`, seen from inside."""
    owned = Path(spec["owned_root"])
    return ProcessorLayout(owned_root=owned, output_root=owned / "output", control_root=CONTAINER_CONTROL_ROOT,
                           python=CONTAINER_INTERPRETER)


async def run_in_container(spec, runtime_config):
    if os.getpid() != 1 or sys.executable != str(CONTAINER_INTERPRETER):
        raise ValueError("CAMPAIGN_PROCESSOR_PRIVATE_CONTAINER_REQUIRED")
    return await run_processor(spec, runtime_config, container_layout(spec))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        spec, runtime = load_processor_spec(args.spec)
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    try:
        return asyncio.run(run_in_container(spec, runtime))
    except (OSError, ValueError, RuntimeError) as error:
        print(f"CAMPAIGN_PROCESSOR_FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
