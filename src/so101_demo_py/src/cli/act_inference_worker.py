"""Task 13 CLI: serve action prefixes for a session from a verified bundle.

The worker runs in the training interpreter — the only place the pinned dependencies exist — reads one
request per line, and writes one reply per line. It never appends into an existing replies file, so a
previous attempt's answers cannot be mistaken for this one's, and it resets the model once for the session
and attempt it was started with.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from so101_demo.act.bundle import load_bundle, load_policy
from so101_demo.act.policy import ActPolicyRunner


def _policy_loader(bundle: dict):
    try:
        import torch  # noqa: F401
    except ImportError as error:
        raise ValueError("INFERENCE_INTERPRETER_REQUIRED") from error
    try:
        from so101_demo.adapters.act.lerobot import build_policy_from_bundle
    except ImportError as error:
        raise ValueError("INFERENCE_ADAPTER_UNAVAILABLE") from error
    return build_policy_from_bundle(bundle)


def main(argv: list[str] | None = None, *, loader=None) -> int:
    parser = argparse.ArgumentParser(prog="act_inference_worker", description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--replies", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--attempt-id", required=True)
    args = parser.parse_args(argv)

    if not args.requests.is_file():
        raise ValueError("INFERENCE_REQUESTS_MISSING")
    if args.replies.exists() or args.replies.is_symlink():
        raise ValueError("INFERENCE_REPLIES_EXIST")
    bundle = load_bundle(args.bundle)
    runner = ActPolicyRunner(bundle, load_policy(args.bundle, loader=loader or _policy_loader))
    runner.reset(args.session_id, args.attempt_id)

    replies = []
    for index, line in enumerate(args.requests.read_text().splitlines()):
        if not line.strip():
            continue
        request = json.loads(line)
        if not isinstance(request, dict) or "observation" not in request:
            raise ValueError("INFERENCE_REQUEST_INVALID")
        prefix = runner.predict(request["observation"], request.get("sequence", index))
        replies.append(json.dumps(prefix, sort_keys=True))
    args.replies.write_text("".join(reply + chr(10) for reply in replies))
    print(json.dumps({"session_id": args.session_id, "attempt_id": args.attempt_id,
                      "replies": len(replies), "execution_prefix": runner.execution_prefix},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
