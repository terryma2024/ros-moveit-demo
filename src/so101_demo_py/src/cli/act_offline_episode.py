"""act_offline_episode: build the sealed episode of an attempt from its raw bag, after the run. See
`act/offline/processor.py`. Exit codes: 0 VALID and QC PASS, 3 INVALID data, 2 refused configuration, 4 infrastructure."""

from __future__ import annotations

from ..act.offline.processor import main

if __name__ == "__main__":
    raise SystemExit(main())
