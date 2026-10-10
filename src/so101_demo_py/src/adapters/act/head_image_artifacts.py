"""Cooperative canonical audit hashing and exclusive durable JSON publication."""
import hashlib
import json
import os
from pathlib import Path
import time

def _audit_chunks(value,*,canonical=False):
    encoder=json.JSONEncoder(sort_keys=True,allow_nan=False,
        **({'separators':(',',':')} if canonical else {}))
    since_yield=0
    for chunk in encoder.iterencode(value):
        yield chunk
        since_yield+=len(chunk)
        if since_yield>=1024:
            time.sleep(0);since_yield=0


def digest(value):
    """Hash canonical audit bytes while yielding between bounded chunks."""
    result=hashlib.sha256()
    for chunk in _audit_chunks(value,canonical=True):result.update(chunk.encode('ascii'))
    return result.hexdigest()


def reference(path):
    path=Path(path).resolve(strict=True)
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def write_json(path,record):
    with Path(path).open('x',encoding='ascii') as handle:
        for chunk in _audit_chunks(record):handle.write(chunk)
        handle.write('\n')
        handle.flush();os.fsync(handle.fileno())
    return reference(path)
