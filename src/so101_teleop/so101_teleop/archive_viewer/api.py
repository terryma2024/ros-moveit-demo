"""Read-only archive endpoints, independent of the control and instance domains."""
from fastapi import APIRouter
from .models import ArchiveConfigView, PackageList
from .scan import ArchiveStore


def archive_router(store: ArchiveStore) -> APIRouter:
    router=APIRouter(prefix='/api/archives',tags=['archives'])

    @router.get('/config',response_model=ArchiveConfigView)
    def config():
        return store.config_view()

    @router.get('/packages',response_model=PackageList)
    def packages(root_id: str,refresh: bool=False):
        return store.packages(root_id,refresh)

    return router
