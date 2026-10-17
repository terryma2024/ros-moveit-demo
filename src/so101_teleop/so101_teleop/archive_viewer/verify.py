"""One owned, cancellable verification thread; no progress is persisted on disk."""
import hashlib
import os
import stat
import threading
from fastapi import HTTPException
from .errors import refuse
from .manifest import ManifestIndex
from .models import VerifyIssue, VerifyProgress
from .paths import read_json, open_readonly


class VerificationManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._thread = None
        self._cancel = threading.Event()
        self._package_id = None
        self._progress = VerifyProgress()
        self._closed = False

    def status(self, package_id):
        with self._lock:
            return self._progress.model_copy(deep=True) if package_id == self._package_id else VerifyProgress()

    def start(self, snapshot):
        with self._lock:
            if self._closed:
                refuse('ARCHIVE_VERIFY_CLOSED', 'verifier is closed', 409)
            if self._thread is not None and self._thread.is_alive():
                refuse('ARCHIVE_VERIFY_BUSY', 'another verification is still active', 409)
            self._cancel = threading.Event()
            self._active_root = snapshot.ref.path
            self._package_id = snapshot.ref.info.package_id
            self._progress = VerifyProgress(state='running')
            self._thread = threading.Thread(target=self._run, args=(snapshot, self._cancel), name='archive-verifier', daemon=False)
            self._thread.start()
            return self._progress.model_copy(deep=True)

    def cancel(self, package_id):
        with self._lock:
            if self._package_id == package_id and self._thread is not None and self._thread.is_alive():
                self._cancel.set()
                if self._progress.state == 'running':
                    self._progress.state = 'cancelling'
            return self.status(package_id)

    def join(self):
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join()

    def close(self):
        with self._lock:
            self._closed = True
            self._cancel.set()
        self.join()

    def _issue(self, name, kind, message):
        with self._lock:
            if kind == 'missing': self._progress.missing_count += 1
            else: self._progress.mismatch_count += 1
            if len(self._progress.issues) < 100:
                self._progress.issues.append(VerifyIssue(name=name, kind=kind, message=message))
            else:
                self._progress.truncated = True

    def _hash_file(self, path, cancel):
        digest = hashlib.sha256();size = 0
        root = getattr(self, '_active_root', path.parent)
        with open_readonly(root, path) as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise OSError('not a regular file')
            while not cancel.is_set():
                raw = stream.read(1024*1024)
                if not raw:
                    return size, digest.hexdigest()
                size += len(raw);digest.update(raw)
        return None

    def _run(self, snapshot, cancel):
        try:
            # Do not trust a cached manifest after start/refresh or a changed seal.
            if read_json(snapshot.resolve('SEALED.json'), 'SEALED.json', root=snapshot.ref.path) != snapshot.ref.seal:
                raise ValueError('seal metadata changed after discovery')
            manifest = ManifestIndex(snapshot.ref)
            with self._lock: self._progress.total = len(manifest.entries)
            for name, entry in manifest.entries.items():
                if cancel.is_set(): break
                lexical = snapshot.ref.path/name
                try:
                    links = [p for p in [lexical, *lexical.parents] if p != snapshot.ref.path.parent and p.is_relative_to(snapshot.ref.path) and p.is_symlink()]
                    if links:
                        resolved = lexical.resolve()
                        if not resolved.is_relative_to(snapshot.ref.path):
                            self._issue(name, 'refused', 'symlink target outside package; not followed')
                        elif len(links) == 1 and links[0] == lexical and entry.get('type') == 'symlink' and entry.get('target', entry.get('link_target')) == os.readlink(lexical):
                            pass
                        else:
                            self._issue(name, 'symlink', 'link identity unavailable or changed; target not read')
                    else:
                        path = snapshot.resolve(name)
                        result = self._hash_file(path, cancel)
                        if result is None: break
                        if result != (entry['bytes'], entry['sha256']):
                            self._issue(name, 'mismatch', 'size or SHA256 differs')
                except FileNotFoundError:
                    self._issue(name, 'missing', 'file is missing')
                except HTTPException as error:
                    self._issue(name, 'missing' if error.status_code == 404 else 'refused', 'file missing' if error.status_code == 404 else 'path refused')
                except OSError:
                    self._issue(name, 'unreadable', 'file cannot be read safely')
                with self._lock: self._progress.checked += 1
            with self._lock:
                self._progress.state = 'cancelled' if cancel.is_set() else 'complete'
        except Exception as error:
            with self._lock:
                self._progress.state = 'failed'
            self._issue('seal-manifest.jsonl', 'failed', 'verification failed: '+type(error).__name__)
