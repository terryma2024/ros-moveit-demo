"""Read-only archive endpoints, independent of the control and instance domains."""
from typing import Literal
from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import StreamingResponse
from .files import FrameResponse
from .models import ArchiveConfigView, PackageList, PackageView, EpisodePage, EpisodeQuery, EpisodeDetail, EpisodeSeries, FileView, VerifyProgress
from .scan import ArchiveStore


def archive_router(store: ArchiveStore) -> APIRouter:
    router=APIRouter(prefix='/api/archives',tags=['archives'])

    @router.get('/config',response_model=ArchiveConfigView)
    def config():
        return store.config_view()

    @router.get('/packages',response_model=PackageList)
    def packages(root_id: str,refresh: bool=False):
        return store.packages(root_id,refresh)

    @router.get('/packages/{package_id}',response_model=PackageView)
    def package(package_id: str):
        return store.package(package_id).view()

    @router.get('/packages/{package_id}/episodes',response_model=EpisodePage)
    def episodes(package_id: str,query: EpisodeQuery = Depends()):
        return store.package(package_id).episodes(query)

    @router.get('/packages/{package_id}/episodes/{scene_id}', response_model=EpisodeDetail)
    def detail(package_id: str, scene_id: str):
        return store.package(package_id).episode(scene_id).detail()

    @router.get('/packages/{package_id}/episodes/{scene_id}/series', response_model=EpisodeSeries)
    def series(package_id: str, scene_id: str):
        return store.package(package_id).episode(scene_id).series()

    @router.get('/packages/{package_id}/episodes/{scene_id}/frames/{row}/{camera}', response_class=StreamingResponse, responses={200: {'content': {'image/png': {'schema': {'type': 'string', 'format': 'binary'}}}}})
    def frame(package_id: str, scene_id: str, camera: Literal['head', 'wrist'], row: int = Path(ge=0)):
        snapshot = store.package(package_id)
        path = snapshot.episode(scene_id).frame(row, camera)
        return FrameResponse(snapshot.ref.path, path)

    @router.get('/packages/{package_id}/episodes/{scene_id}/files/{file_id}', response_model=FileView)
    def file(package_id: str, scene_id: str, file_id: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
        return store.package(package_id).episode(scene_id).file(file_id, offset, limit)

    @router.get('/packages/{package_id}/episodes/{scene_id}/files/{file_id}/download', response_class=StreamingResponse, responses={200: {'content': {'image/png': {'schema': {'type': 'string', 'format': 'binary'}}}}})
    def download(package_id: str, scene_id: str, file_id: str):
        snapshot = store.package(package_id)
        path = snapshot.episode(scene_id).png(file_id)
        return FrameResponse(snapshot.ref.path, path, download=True)

    @router.post('/packages/{package_id}/verify', response_model=VerifyProgress)
    def start_verify(package_id: str):
        return store.verifier.start(store.package(package_id))

    @router.get('/packages/{package_id}/verify', response_model=VerifyProgress)
    def verify(package_id: str):
        return store.verifier.status(package_id)

    @router.delete('/packages/{package_id}/verify', response_model=VerifyProgress)
    def cancel_verify(package_id: str):
        return store.verifier.cancel(package_id)

    return router
