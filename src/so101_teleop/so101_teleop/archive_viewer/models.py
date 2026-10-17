"""Public archive contracts; filesystem paths never grant client authority."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ArchiveModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class RootView(ArchiveModel):
    root_id: str
    label: str


class ArchiveConfigView(ArchiveModel):
    enabled: bool
    roots: list[RootView]


class PackageInfo(ArchiveModel):
    package_id: str
    name: str
    kind: Literal['collection','supporting']
    sealed_at: str | None = None
    reason: str | None = None
    files: int = 0
    bytes: int = 0
    manifest_sha256: str | None = None
    registered: bool = False


class PackageList(ArchiveModel):
    packages: list[PackageInfo]
    warnings: list[str] = Field(default_factory=list)
