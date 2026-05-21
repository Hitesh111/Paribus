from typing import Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from app.clients import CreatedHospital
from app.dependencies import get_batch_store, get_bulk_processor, get_directory_client
from app.exceptions import HospitalDirectoryAPIError
from app.main import app
from app.models import HospitalCsvRow
from app.store import BatchStore


class FakeHospitalDirectoryClient:
    def __init__(
        self,
        create_map: Optional[Dict[str, int]] = None,
        fail_names: Optional[List[str]] = None,
        activate_failure: Optional[str] = None,
    ) -> None:
        self.create_map = create_map or {}
        self.fail_names = set(fail_names or [])
        self.activate_failure = activate_failure
        self.created_payloads: List[Dict[str, object]] = []
        self.activated_batches: List[str] = []

    async def create_hospital(self, row: HospitalCsvRow, batch_id: str) -> CreatedHospital:
        self.created_payloads.append(
            {
                "batch_id": batch_id,
                "row_number": row.row_number,
                "name": row.name,
                "address": row.address,
                "phone": row.phone,
            }
        )
        if row.name in self.fail_names or row.name.startswith("FAIL_"):
            raise HospitalDirectoryAPIError("create hospital", f"Simulated upstream creation failure for '{row.name}' (Triggered by FAIL_ prefix)", 422)
        hospital_id = self.create_map.get(row.name, 1000 + row.row_number)
        return CreatedHospital(hospital_id=hospital_id, raw={"id": hospital_id})

    async def activate_batch(self, batch_id: str) -> None:
        self.activated_batches.append(batch_id)
        if self.activate_failure is not None:
            raise HospitalDirectoryAPIError("activate batch", self.activate_failure, 502)


@pytest.fixture()
def fresh_store() -> BatchStore:
    return BatchStore()


@pytest.fixture()
def fake_client() -> FakeHospitalDirectoryClient:
    return FakeHospitalDirectoryClient()


@pytest.fixture()
def client(fresh_store: BatchStore, fake_client: FakeHospitalDirectoryClient) -> TestClient:
    app.dependency_overrides[get_batch_store] = lambda: fresh_store
    app.dependency_overrides[get_directory_client] = lambda: fake_client
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
