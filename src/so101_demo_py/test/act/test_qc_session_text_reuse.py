"""Readback reuses the strict text parse of a file instead of parsing the same file again.

The engine's readback reads `events.jsonl` leniently right after `verify_audit_manifest` has read it strictly with the same
`Path.read_text().splitlines()`; when the strict parse succeeded every line was a JSON document, so the lenient filter removes
nothing and the lists are equal. `cached_lines(..., reuse_text_strict=True)` returns the strict list for the same file signature,
only when the strict parse is recorded as a text parse (`text_origin=True`).
"""

import os
import random

from so101_demo.act.qc_session import cached_lines
from so101_demo.act.qc_session import qc_session as session_scope


def strict_text(path):
    from so101_demo.act.episode_audit.checks import _parse_audit_lines
    return _parse_audit_lines(path)


def lenient_text(path):
    from so101_demo.act.episode_qc import _parse_stream_rows
    return _parse_stream_rows(path)


def counting_parsers():
    calls = {"strict": 0, "lenient": 0}

    def strict(path):
        calls["strict"] += 1
        return strict_text(path)

    def lenient(path):
        calls["lenient"] += 1
        return lenient_text(path)

    return strict, lenient, calls


def test_a_lenient_read_with_the_opt_in_reuses_the_text_strict_parse(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"a":1}\n{"b":2}\n')
    strict, lenient, calls = counting_parsers()
    with session_scope() as session:
        first = cached_lines(path, strict, text_origin=True)
        second = cached_lines(path, lenient, "lenient", reuse_text_strict=True)
        assert second is first and calls == {"strict": 1, "lenient": 0}
        assert second == [{"a": 1}, {"b": 2}] == lenient_text(path)
        assert session.hits == 1 and session.misses == 1


def test_without_the_opt_in_or_without_a_text_origin_the_lenient_read_parses_as_before(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"a":1}\n')
    strict, lenient, calls = counting_parsers()
    with session_scope():
        cached_lines(path, strict, text_origin=True)
        cached_lines(path, lenient, "lenient")                                   # no opt-in
        assert calls == {"strict": 1, "lenient": 1}
    strict, lenient, calls = counting_parsers()
    with session_scope():
        cached_lines(path, strict)                                               # a strict parse of unknown (bytes) origin
        cached_lines(path, lenient, "lenient", reuse_text_strict=True)
        assert calls == {"strict": 1, "lenient": 1}
    strict, lenient, calls = counting_parsers()
    cached_lines(path, lenient, "lenient", reuse_text_strict=True)               # no session: nothing is kept
    cached_lines(path, lenient, "lenient", reuse_text_strict=True)
    assert calls["lenient"] == 2


def test_the_opt_in_does_not_leak_into_later_reads_without_it(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"a":1}\n')
    strict, lenient, calls = counting_parsers()
    with session_scope():
        cached_lines(path, strict, text_origin=True)
        cached_lines(path, lenient, "lenient", reuse_text_strict=True)
        cached_lines(path, lenient, "lenient")
        assert calls == {"strict": 1, "lenient": 1}


def test_a_changed_file_is_parsed_again_even_with_the_opt_in(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"a":1}\n')
    strict, lenient, calls = counting_parsers()
    with session_scope():
        cached_lines(path, strict, text_origin=True)
        status = path.stat()
        os.utime(path, ns=(status.st_atime_ns, status.st_mtime_ns + 7_000_000_000))
        rows = cached_lines(path, lenient, "lenient", reuse_text_strict=True)
        assert rows == [{"a": 1}] and calls == {"strict": 1, "lenient": 1}
        path.write_text('{"a":1}\n{"b":2}\n')
        assert cached_lines(path, lenient, "lenient", reuse_text_strict=True) == [{"a": 1}, {"b": 2}]
        assert calls["lenient"] == 2


def corpus_files():
    """Raw JSONL texts (bytes): the line terminators and blank lines the two text parsers could treat differently."""
    row = '{"k":"v"}'
    unusual = ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", " ", " "]
    texts = [b"", b"\n", row.encode(), (row + "\n").encode(), (row + "\n\n" + row + "\n").encode(),
             (row + "\n   \n" + row + "\n").encode(), (row + "\r\n" + row + "\r\n").encode(),
             (row + "\r" + row + "\r").encode(), (row + "\n" + row).encode(), ("﻿" + row + "\n").encode(),
             (row + " \n" + row + "\t\n").encode(), (row + "\x0b\n").encode(), b'{"k":"\xff"}\n']
    for character in unusual:
        texts.append(('{"k":"a%sb"}\n' % character).encode())               # raw inside a JSON string
        texts.append((row + character + row + "\n").encode())                # between two documents
        texts.append((row + "\n" + character + "\n" + row + "\n").encode())  # alone on a line
    return texts


def test_whenever_the_strict_text_parse_succeeds_the_lenient_text_parse_gives_the_same_rows(tmp_path):
    texts = corpus_files()
    rng = random.Random(20261014)
    pieces = [b'{"k":1}', b'{"k":"a\\u2028b"}', b"", b"  ", b"\r", b"\x0b", "\x85".encode(), " ".encode(), b"\n"]
    for _ in range(300):
        texts.append(b"".join(rng.choice(pieces) + rng.choice([b"\n", b"\r\n", b"", b"\r"]) for _ in range(rng.randrange(0, 6))))
    both = 0
    for index, text in enumerate(texts):
        path = tmp_path / f"f{index}.jsonl"
        path.write_bytes(text)
        try:
            strict = strict_text(path)
        except Exception:
            continue                    # strict refused it: the opt-in never applies
        both += 1
        assert lenient_text(path) == strict, text
    assert both > 40
