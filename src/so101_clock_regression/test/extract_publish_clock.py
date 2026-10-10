"""Extract one current production method, preserving its bytes and failing closed."""

import hashlib
from pathlib import Path
import sys


def extract(source):
    signature = "void MujocoSimulation::publish_clock()"
    if source.count(signature) != 1:
        raise ValueError("Expected exactly one publish_clock definition")
    start = source.index(signature)
    opening = source.index("{", start + len(signature))
    if source[start + len(signature):opening].strip():
        raise ValueError("Unexpected publish_clock declaration")
    depth = 0
    mode = "code"
    escaped = False
    index = opening
    while index < len(source):
        char = source[index]
        pair = source[index:index + 2]
        if mode == "line":
            if char == "\n":
                mode = "code"
        elif mode == "block":
            if pair == "*/":
                mode = "code"
                index += 1
        elif mode in ("'", '"'):
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == mode:
                mode = "code"
        elif pair == "//":
            mode = "line"
            index += 1
        elif pair == "/*":
            mode = "block"
            index += 1
        elif char in ("'", '"'):
            # Raw literals require a different lexer: refuse rather than misextract.
            if char == '"' and source[index - 1:index] == "R":
                raise ValueError("Raw literal requires extraction support")
            mode = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
        index += 1
    raise ValueError("Unterminated publish_clock definition")


if __name__ == "__main__":
    source_path, output_path = map(Path, sys.argv[1:])
    method = extract(source_path.read_text()) + "\n"
    output_path.write_text(method)
    print("publish_clock_body_sha256=" + hashlib.sha256(method.encode()).hexdigest())
