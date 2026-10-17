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


class SealView(ArchiveModel):
    kind: str
    sealed_at: str | None = None
    reason: str | None = None
    files: int = 0
    bytes: int = 0
    manifest_sha256: str | None = None


class IdentityValue(ArchiveModel):
    value: str | int | float | bool | None = None
    source: str | None = None


class Metric(ArchiveModel):
    total: float
    median: float | None = None


class PackageStatistics(ArchiveModel):
    planned: int
    committed: int
    non_committed_by_outcome: dict[str, int]
    committed_by_split: dict[str, int]
    retry_rounds_run: int
    recovered: int
    recovered_by_round: dict[str, int]
    duration_rows: Metric
    duration_seconds: Metric
    episode_bytes: Metric


class PackageView(ArchiveModel):
    package: PackageInfo
    seal: SealView
    identity: dict[str, IdentityValue]
    statistics: PackageStatistics | None = None
    warnings: list[str] = Field(default_factory=list)


class EpisodeRow(ArchiveModel):
    scene_id: str
    split: str | None = None
    collection_committed: bool
    outcome: Literal['VALID', 'INVALID', 'FAULT', 'MISSING']
    reason: str | None = None
    recording_attempt_count: int
    final_recording_round: int
    record_count: int | None = None
    duration_s: float | None = None
    bytes: int | None = None
    teacher_result: str | None = None
    qc_status: str | None = None


class EpisodeQuery(ArchiveModel):
    split: Literal['train', 'validation', 'offline_test'] | None = None
    outcome: Literal['VALID', 'INVALID', 'FAULT', 'MISSING'] | None = None
    q: str = Field(default='', max_length=128)
    sort: str = 'scene_id'
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=200)


class EpisodePage(ArchiveModel):
    episodes: list[EpisodeRow]
    total: int
