"""The JSONL line parsers read a file line by line instead of holding its whole text and a list of its lines.

`_parse_stream_rows` (lenient), `_parse_audit_lines` (strict) and the QC's bytes reader each have a whole-file original
(`*_whole`) and a streaming entry point that falls back to the original on any exception. For every input the entry point must give
the original's list, or raise the original's exception (same type and same text), and on a large file it must peak lower by most
of the file's size.
"""

import os
import random
import re
import tracemalloc

import pytest
from so101_demo.act import episode_qc
from so101_demo.act.episode_audit import checks, formal_coverage
from test_qc_session_text_reuse import corpus_files


def outcome(function, path):
    try:
        return ("rows", function(path))
    except Exception as error:      # noqa: BLE001 - the outcome includes which exception
        # reading a directory through a file descriptor names the descriptor number, which is the process's, not the parser's
        return ("raised", type(error), re.sub(r"Is a directory: \d+", "Is a directory: <fd>", str(error)))


def generated_texts():
    rng = random.Random(20261015)
    pieces = [b'{"k":1}', b'{"k":"a\\u2028b"}', b'{"k":"\xc3\xa9"}', b"", b"  ", b"\r", b"\x0b", "\x85".encode(), " ".encode(),
              b"\n", b"{", b'{"k":"\xff"}', b"\xe4"]
    texts = corpus_files()
    texts.append(b'{"k":"\xe4"}\n')                                                    # truncated multi-byte sequence
    texts.append(('{"k":"%s"}\n' % ("é" * 20000)).encode())                       # characters straddle read-chunk boundaries
    texts.append(('{"k":"%s"}\n' % ("中" * 9000)).encode() * 3)
    texts.append(b'{"k":1}\n' * 3000 + b'{"k":\n' + b'{"k":1}\n' * 10)                 # a bad line deep in the file
    for _ in range(300):
        texts.append(b"".join(rng.choice(pieces) + rng.choice([b"\n", b"\r\n", b"", b"\r"]) for _ in range(rng.randrange(0, 7))))
    return texts


PARSERS = [
    pytest.param(episode_qc._parse_stream_rows, episode_qc._parse_stream_rows_whole, id="lenient"),
    pytest.param(checks._parse_audit_lines, checks._parse_audit_lines_whole, id="strict"),
    pytest.param(episode_qc._original_rows, episode_qc._original_rows_whole, id="bytes"),
]


@pytest.mark.parametrize("streaming, whole", PARSERS)
def test_the_streaming_parser_gives_the_original_result_or_the_original_exception(tmp_path, streaming, whole):
    texts = generated_texts()
    rows = raised = 0
    for index, text in enumerate(texts):
        path = tmp_path / f"f{index}.jsonl"
        path.write_bytes(text)
        expected, actual = outcome(whole, path), outcome(streaming, path)
        assert actual == expected, (index, text[:80])
        rows += expected[0] == "rows"
        raised += expected[0] == "raised"
    assert rows > 40 and raised > 40


def test_the_strict_parser_is_the_one_the_audit_modules_call():
    assert formal_coverage._parse_audit_lines is checks._parse_audit_lines


def test_a_missing_file_raises_the_originals_error(tmp_path):
    for streaming, whole in ((episode_qc._parse_stream_rows, episode_qc._parse_stream_rows_whole),
                             (checks._parse_audit_lines, checks._parse_audit_lines_whole)):
        assert outcome(streaming, tmp_path / "absent")[:2] == outcome(whole, tmp_path / "absent")[:2]
        assert outcome(streaming, tmp_path / "absent")[1] is FileNotFoundError


def test_the_bytes_reader_refuses_what_the_original_refuses(tmp_path):
    (tmp_path / "directory").mkdir()
    (tmp_path / "real.jsonl").write_bytes(b'{"k":1}\n')
    os.symlink(tmp_path / "real.jsonl", tmp_path / "link.jsonl")
    for name in ("directory", "link.jsonl", "absent", "relative"):
        target = tmp_path / name if name != "relative" else "relative/../x"
        assert outcome(episode_qc._original_rows, target) == outcome(episode_qc._original_rows_whole, target)


def build_big_file(path, rows=20000, pad=1000):
    with open(path, "w") as stream:
        for index in range(rows):
            stream.write('{"i":%d,"pad":"%s"}\n' % (index, chr(97 + index % 26) * pad))
    return os.path.getsize(path)


def peak_of(function, path):
    tracemalloc.start()
    try:
        result = function(path)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    return peak, len(result)


@pytest.mark.parametrize("streaming, whole", PARSERS)
def test_the_streaming_parser_peaks_lower_by_most_of_the_file_size(tmp_path, streaming, whole):
    path = tmp_path / "big.jsonl"
    size = build_big_file(path)
    assert size > 18_000_000
    whole_peak, whole_count = peak_of(whole, path)
    stream_peak, stream_count = peak_of(streaming, path)
    assert stream_count == whole_count == 20000
    assert whole_peak - stream_peak >= 0.8 * size, (whole_peak, stream_peak, size)


@pytest.mark.parametrize("streaming, whole", PARSERS)
def test_a_failing_file_does_not_keep_the_partial_rows_while_the_original_runs(tmp_path, streaming, whole):
    path = tmp_path / "bad-tail.jsonl"
    size = build_big_file(path)
    with open(path, "a") as stream:
        stream.write("{not json\n")

    def raising(function):
        def run(target):
            try:
                function(target)
            except ValueError:
                return []
            raise AssertionError("the file must be refused")
        return run

    whole_peak, _ = peak_of(raising(whole), path)
    stream_peak, _ = peak_of(raising(streaming), path)
    assert stream_peak <= whole_peak + 0.1 * size, (whole_peak, stream_peak, size)
