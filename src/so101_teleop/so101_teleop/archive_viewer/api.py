"""Read-only archive endpoints, independent of the control and instance domains."""
from fastapi import APIRouter, Depends
from .models import ArchiveConfigView, PackageList, PackageView, EpisodePage, EpisodeQuery
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

    return router
