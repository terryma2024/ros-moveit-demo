"""Explicit search roots; archive access is opt-in."""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArchiveConfig:
    roots: tuple[Path, ...] = ()

    def __post_init__(self):
        roots=[]
        for value in self.roots:
            root=Path(value)
            if not root.is_absolute() or not root.is_dir():
                raise ValueError('ARCHIVE_ROOT_INVALID: expected an existing absolute directory')
            root=root.resolve()
            if root not in roots: roots.append(root)
        object.__setattr__(self, 'roots', tuple(roots))
