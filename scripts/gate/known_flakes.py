#!/usr/bin/env python3
"""Parse and validate known-flakes.txt.

Line format: `<test id substring> | <reason> | <date added>`. Blank lines and lines starting with `#` are ignored.
The substring is matched against the id of a failing test (pytest node id, or the gtest / launch test name).
The date is YYYY-MM-DD. A malformed line is an error: the rerun that reads this file refuses to run.

usage: known_flakes.py <known-flakes.txt>    prints one substring per line; exit 1 and a message on stderr for a bad file.
"""
import datetime
import sys
from pathlib import Path


class KnownFlakeError(ValueError):
    pass


def parse(text):
    """Return [(substring, reason, date)] or raise KnownFlakeError naming the first bad line."""
    entries = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split(" | ")
        if len(parts) != 3:
            raise KnownFlakeError(f"line {number}: expected '<test id substring> | <reason> | <date added>': {line!r}")
        substring, reason, date = parts
        if not substring or substring != substring.strip() or "|" in substring:
            raise KnownFlakeError(f"line {number}: empty or padded test id substring: {line!r}")
        if not reason.strip() or "|" in reason:
            raise KnownFlakeError(f"line {number}: empty reason: {line!r}")
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            raise KnownFlakeError(f"line {number}: date must be YYYY-MM-DD, got {date!r}") from None
        entries.append((substring, reason.strip(), date))
    return entries


def load(path):
    return parse(Path(path).read_text(encoding="utf-8"))


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        entries = load(argv[1])
    except (OSError, KnownFlakeError) as error:
        print(f"known-flakes: {error}", file=sys.stderr)
        return 1
    for substring, _reason, _date in entries:
        print(substring)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
