from fastapi import Depends

from .clients import HospitalDirectoryClient
from .config import Settings, get_settings
from .processor import BulkHospitalProcessor
from .store import BatchStore

import httpx

_BATCH_STORE = BatchStore()
_HTTP_CLIENT: httpx.AsyncClient = None  # type: ignore

def get_http_client(settings: Settings = Depends(get_settings)) -> httpx.AsyncClient:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        _HTTP_CLIENT = httpx.AsyncClient(
            base_url=settings.hospital_directory_api_base_url,
            timeout=settings.request_timeout_seconds
        )
    return _HTTP_CLIENT


def get_batch_store() -> BatchStore:
    return _BATCH_STORE


def get_directory_client(client: httpx.AsyncClient = Depends(get_http_client)) -> HospitalDirectoryClient:
    return HospitalDirectoryClient(client)


async def get_bulk_processor(
    client: HospitalDirectoryClient = Depends(get_directory_client),
    store: BatchStore = Depends(get_batch_store),
    settings: Settings = Depends(get_settings),
) -> BulkHospitalProcessor:
    return BulkHospitalProcessor(client, store, settings)

