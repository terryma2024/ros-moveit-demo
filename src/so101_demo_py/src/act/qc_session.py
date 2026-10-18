"""A per-process, per-session memo of the pure verifiers a QC recomputation repeats.

A full QC reads the same sealed files through several routes: the audit manifest is verified four times, the native events twice,
the seal twice, the execution snapshot thirty-odd times. Each verifier is a pure function of the files it reads. Inside a
`qc_session()` the result of such a call is kept, keyed on the arguments **and on the signature of every file the call reads**
(path, size, inode, mtime), so a second call over the same files in the same process returns the first call's result instead of
repeating the work. Outside a session nothing is kept and every caller behaves as before.

What this is not: it never crosses a process (nothing is written to disk), never trusts the offline processor's QC memo, and is
dropped when the session ends. A verifier that raises is not remembered; the exception propagates as before. A file that changes
between two calls changes the signature, so its verifier runs again.
"""

from __future__ import annotations

import contextlib
import copy
import functools
import io
import os
import pickle
from pathlib import Path

_STACK: list = []
#: the only owners that may hold a session while the export path runs: the readback entry points (`act_diagnostic_episode qc`,
#: `verify-commit`, `check-export`, `readback`). A session opened anywhere else (bundle.py, training, a library) makes the export
#: path refuse: a cached proof grants no eligibility, and only an entry point may share a recomputation between its stages.
ENTRY_OWNERS = frozenset({"readback:qc", "readback:verify-commit", "readback:check-export", "readback:readback"})


class QcSession:
    """The memo of one session, with counters (for the readback receipt and the tests)."""

    def __init__(self, owner: str = "internal") -> None:
        self.owner = owner
        #: report-level reuse of full QC recomputations (entry-point sessions only): key -> {"fingerprint", "report"}
        self.qc_results: dict = {}
        self.qc_hits = 0
        #: set by `act_diagnostic_episode readback`: the inputs it watches and the content fingerprint taken at its start
        self.watch = None
        self.input_fingerprint = None
        self.cache: dict = {}
        self.hits = 0
        self.misses = 0
        self.computations: dict = {}

    def note(self, name: str) -> None:
        self.computations[name] = self.computations.get(name, 0) + 1


@contextlib.contextmanager
def qc_session(owner: str = "internal"):
    session = QcSession(owner)
    _STACK.append(session)
    try:
        yield session
    finally:
        _STACK.pop()


def active() -> QcSession | None:
    return _STACK[-1] if _STACK else None


def joined_session():
    """A session scope that joins the enclosing session when one is open and otherwise opens (and closes) a fresh one."""
    return contextlib.nullcontext() if active() is not None else qc_session()


def assert_export_path_allowed() -> None:
    """Called at the top of the export functions: a session that is not a readback entry point's is refused there."""
    session = active()
    if session is not None and session.owner not in ENTRY_OWNERS:
        raise ValueError("QC_SESSION_IN_EXPORT_PATH")


def file_signature(path) -> tuple:
    path = os.fspath(path)
    try:
        status = os.stat(path)
    except OSError:
        return (path, None)
    return (path, status.st_size, status.st_ino, status.st_mtime_ns)


def tree_signature(root) -> tuple:
    """The signature of every file below `root`, sorted: a changed, added, removed or replaced file changes it."""
    items = []
    stack = [os.fspath(root)]
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    else:
                        status = entry.stat(follow_symlinks=False)
                        items.append((entry.path, status.st_size, status.st_ino, status.st_mtime_ns))
        except OSError:
            items.append((directory, None))
    items.sort()
    return tuple(items)


class Identity:
    """A dict key that holds an object and compares by identity (so the object cannot be freed and its id reused)."""

    __slots__ = ("value",)

    def __init__(self, value) -> None:
        self.value = value

    def __hash__(self) -> int:
        return id(self.value)

    def __eq__(self, other) -> bool:
        return isinstance(other, Identity) and other.value is self.value


def content_bytes(value) -> bytes:
    """The type-exact serialisation of a plain document, for a content key. Pickle keeps types (1, 1.0 and True, or int and str
    dictionary keys, never give the same bytes), and with its memo switched off the bytes do not depend on which parse shared which
    string objects. Equal bytes mean an equal value; a different dictionary order only costs a miss. Raises for a value pickle
    cannot serialise (and for a recursive one): the caller then keys by identity or does not memoise."""
    buffer = io.BytesIO()
    pickler = pickle.Pickler(buffer, protocol=5)
    pickler.fast = True
    pickler.dump(value)
    return buffer.getvalue()


def session_memo(key_function, *, copy_result: bool = True):
    """Memoise a pure verifier inside a session. `key_function(*args, **kwargs)` returns a hashable key that includes the
    signatures of the files the call reads. The result is deep-copied in and out unless `copy_result` is false."""

    def decorate(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            session = active()
            if session is None:
                return function(*args, **kwargs)
            key = (function.__module__, function.__qualname__, key_function(*args, **kwargs))
            if key in session.cache:
                session.hits += 1
                stored = session.cache[key]
                return copy.deepcopy(stored) if copy_result else stored
            result = function(*args, **kwargs)
            session.misses += 1
            session.note(function.__qualname__)
            session.cache[key] = copy.deepcopy(result) if copy_result else result
            return result
        return wrapper
    return decorate


def cached_lines(path, parse, kind="strict", *, text_origin=False, reuse_text_strict=False):
    """`parse(path)` for a file, remembered per file signature inside a session. `kind` names the parse ("strict": every line is
    JSON; "lenient": blank lines are skipped): parses of the same kind must give the same value. The returned object is shared
    between callers, so callers must treat it as read-only.

    `text_origin=True` says the strict `parse` is `Path.read_text().splitlines()` over JSON lines, and the session notes that beside
    the entry. `reuse_text_strict=True` lets a "lenient" read of the same file signature take that entry instead of parsing again.
    This is sound only because the two are the same text read the same way: a strict parse that succeeded found every line to be a
    JSON document, and `json.loads` refuses a line that is empty or only whitespace, so the lenient filter would have removed
    nothing. A strict entry whose origin is not noted (the QC's bytes reader) is never taken, and a read without the flag never
    looks at the note."""
    session = active()
    if session is None:
        return parse(path)
    signature = file_signature(path)
    key = ("lines", kind, signature)
    if key in session.cache:
        session.hits += 1
        return session.cache[key]
    if reuse_text_strict and kind == "lenient" and session.cache.get(("lines-origin", "strict", signature)) == "text":
        shared = session.cache.get(("lines", "strict", signature))
        if shared is not None:
            session.hits += 1
            return shared
    result = parse(path)
    session.misses += 1
    session.cache[key] = result
    if text_origin and kind == "strict":
        session.cache[("lines-origin", kind, signature)] = "text"
    return result


def load_model(scene_path, *, root=None):
    """`mujoco.MjModel.from_xml_path(scene_path)`, shared inside a session (keyed on the tree under `root`, default the scene's
    directory)."""
    import mujoco

    path = Path(scene_path)
    session = active()
    if session is None:
        return mujoco.MjModel.from_xml_path(str(path))
    key = ("model", str(path.absolute()), tree_signature(path.parent if root is None else root))
    model = session.cache.get(key)
    if model is None:
        model = session.cache[key] = mujoco.MjModel.from_xml_path(str(path))
        session.misses += 1
        session.note("MjModel.from_xml_path")
    else:
        session.hits += 1
    return model
