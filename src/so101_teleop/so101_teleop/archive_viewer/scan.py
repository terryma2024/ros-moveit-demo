"""Directory discovery and bounded, in-memory package ownership."""
import hashlib
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from fastapi import HTTPException
from .config import ArchiveConfig
from .models import ArchiveConfigView, RootView, PackageInfo, PackageList
from .paths import read_json
from .errors import refuse


def opaque_id(path: Path) -> str:
    return hashlib.sha256(os.fsencode(path)).hexdigest()[:24]


@dataclass(frozen=True)
class PackageRef:
    path: Path
    recorded_root: Path
    seal: dict
    info: PackageInfo


class ArchiveStore:
    def __init__(self,config: ArchiveConfig):
        from .verify import VerificationManager
        self.verifier=VerificationManager()
        self.config=config
        self.roots={opaque_id(root):root for root in config.roots}
        self._scans={}
        self._packages=OrderedDict()
        self.refs={}
        self._records=OrderedDict()
        self._records_lock=threading.RLock()
        self._lock=threading.RLock()

    def config_view(self) -> ArchiveConfigView:
        return ArchiveConfigView(enabled=bool(self.roots), roots=[RootView(root_id=key,label=root.name) for key,root in self.roots.items()])

    def packages(self,root_id: str,refresh: bool=False) -> PackageList:
        root=self.roots.get(root_id)
        if root is None: refuse('ARCHIVE_ROOT_NOT_FOUND','unknown root id')
        with self._lock:
            if not refresh and root_id in self._scans: return self._scans[root_id]
            warnings=[]; registered=set(); found={}
            registry=root/'SEALED-ROOTS.json'
            if registry.is_file() and not registry.is_symlink():
                try:
                    document=read_json(registry,'SEALED-ROOTS.json',root=root)
                    for row in document.get('roots',[]):
                        value=Path(row.get('root',''))
                        if value.is_absolute(): registered.add(value)
                except (HTTPException,TypeError,AttributeError): warnings.append('SEALED-ROOTS.json: invalid registry')
            pending=[root]
            while pending:
                directory=pending.pop()
                try:
                    with os.scandir(directory) as stream: entries=list(stream)
                except OSError:
                    warnings.append(f'{directory.relative_to(root)}: unreadable directory');continue
                marker=next((entry for entry in entries if entry.name=='SEALED.json'),None)
                if marker is not None:
                    try:
                        if marker.is_symlink(): raise ValueError('symlinked seal')
                        seal=read_json(directory/'SEALED.json','SEALED.json',root=directory)
                        if seal.get('kind')!='SEALED_EVIDENCE_ROOT': raise ValueError('unsupported seal kind')
                        recorded=Path(seal.get('root',str(directory)))
                        if not recorded.is_absolute(): raise ValueError('invalid recorded root')
                        pid=opaque_id(directory)
                        info=PackageInfo(package_id=pid,name=directory.name,kind='collection' if any(e.name=='collection-index.json' for e in entries) else 'supporting',sealed_at=seal.get('sealed_at'),reason=seal.get('reason'),files=seal.get('files',0),bytes=seal.get('bytes',0),manifest_sha256=seal.get('manifest_sha256'),registered=directory in registered or recorded in registered)
                        found[pid]=PackageRef(directory,recorded,seal,info)
                    except (HTTPException,ValueError,TypeError): warnings.append(f'{directory.relative_to(root)}/SEALED.json: invalid seal')
                    continue
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False): pending.append(Path(entry.path))
            result=PackageList(packages=sorted((r.info for r in found.values()),key=lambda p:p.name),warnings=warnings)
            old=self._scans.get(root_id)
            if old:
                for row in old.packages: self.refs.pop(row.package_id,None)
            if refresh: self._packages.clear()
            self.refs.update(found);self._scans[root_id]=result
            return result

    def reference(self,package_id: str) -> PackageRef:
        with self._lock:
            if package_id not in self.refs:
                for root_id in self.roots: self.packages(root_id)
            ref=self.refs.get(package_id)
            if ref is None: refuse('ARCHIVE_PACKAGE_NOT_FOUND','unknown package id')
            return ref

    def package(self, package_id: str):
        from .package import PackageSnapshot
        with self._lock:
            ref = self.reference(package_id)
            cached = self._packages.pop(package_id, None)
            if cached is None or cached.ref is not ref:
                cached = PackageSnapshot(ref, self._records, self._records_lock)
            self._packages[package_id] = cached
            while len(self._packages) > 2:
                self._packages.popitem(last=False)
            return cached
