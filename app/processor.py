import asyncio
from typing import List

from .clients import HospitalDirectoryClient
from .config import Settings
from .exceptions import HospitalDirectoryAPIError
from .models import BatchRecord, HospitalCsvRow
from .schemas import BulkBatchStatusResponse, BulkProcessingResponse, CsvPreviewRow, CsvValidationResponse
from .store import BatchStore
from .parser import parse_hospital_csv, preview_rows


class BulkHospitalProcessor:
    def __init__(self, client: HospitalDirectoryClient, store: BatchStore, settings: Settings) -> None:
        self._client = client
        self._store = store
        self._settings = settings
        self._semaphore = asyncio.Semaphore(settings.concurrency_limit)

    async def process_new_batch(self, rows: List[HospitalCsvRow]) -> BulkProcessingResponse:
        batch = self._store.create_batch(rows)
        await self._run_batch(batch.batch_id, candidate_rows=[row.row_number for row in rows])
        return self.build_processing_response(batch.batch_id)

    async def resume_batch(self, batch_id: str) -> BulkProcessingResponse:
        batch = self._store.batch_snapshot(batch_id)

        if batch.batch_activated and batch.failed_hospitals == 0 and batch.status == "completed":
            return self.build_processing_response(batch_id)

        failed_rows = [
            row_number
            for row_number, result in sorted(batch.results.items())
            if result.status == "failed"
        ]

        if not failed_rows and batch.failed_hospitals == 0 and not batch.batch_activated:
            await self._attempt_activation(batch_id)
            return self.build_processing_response(batch_id)

        if failed_rows:
            await self._run_batch(batch_id, candidate_rows=failed_rows, resume=True)
        else:
            await self._attempt_activation(batch_id)
        return self.build_processing_response(batch_id)

    async def validate_csv(self, content: bytes) -> CsvValidationResponse:
        rows = parse_hospital_csv(content, self._settings)
        preview = [CsvPreviewRow(row=row.row_number, name=row.name, address=row.address, phone=row.phone) for row in preview_rows(rows)]
        return CsvValidationResponse(valid=True, total_hospitals=len(rows), preview=preview, errors=[])

    def build_processing_response(self, batch_id: str) -> BulkProcessingResponse:
        record = self._store.batch_snapshot(batch_id)
        return record_to_processing_response(record)

    def build_status_response(self, batch_id: str) -> BulkBatchStatusResponse:
        record = self._store.batch_snapshot(batch_id)
        return record_to_status_response(record)

    async def _run_batch(self, batch_id: str, candidate_rows: List[int], resume: bool = False) -> None:
        record = self._store.mark_processing(batch_id)
        
        async def process_row(row_number: int) -> None:
            row = record.rows[row_number]
            try:
                # Limit the concurrent requests to the upstream directory service.
                # Helps us stay below Cloudflare's rate limit threshold and avoids triggering transient 429s.
                async with self._semaphore:
                    created = await self._client.create_hospital(row, batch_id)

            except HospitalDirectoryAPIError as exc:
                self._store.mark_row_failure(batch_id, row_number, str(exc))
                return
            self._store.mark_row_success(batch_id, row_number, created.hospital_id)

        await asyncio.gather(*(process_row(row_number) for row_number in candidate_rows))

        record = self._store.batch_snapshot(batch_id)
        if record.failed_hospitals > 0:
            self._store.mark_completed_with_failures(batch_id)
            return

        if record.total_hospitals == 0:
            self._store.mark_completed_with_failures(batch_id)
            return

        if resume or not record.batch_activated:
            await self._attempt_activation(batch_id)

    async def _attempt_activation(self, batch_id: str) -> None:
        try:
            await self._client.activate_batch(batch_id)
        except HospitalDirectoryAPIError as exc:
            self._store.mark_activation_failure(batch_id, str(exc))
            return
        self._store.mark_activation_success(batch_id)


def record_to_processing_response(record: BatchRecord) -> BulkProcessingResponse:
    from .schemas import HospitalRowResponse

    hospitals = [
        HospitalRowResponse(
            row=result.row,
            hospital_id=result.hospital_id,
            name=result.name,
            status=result.status,
            error=result.error,
        )
        for result in record.ordered_results()
    ]
    return BulkProcessingResponse(
        batch_id=record.batch_id,
        total_hospitals=record.total_hospitals,
        processed_hospitals=record.processed_hospitals,
        failed_hospitals=record.failed_hospitals,
        processing_time_seconds=record.elapsed_seconds(),
        batch_activated=record.batch_activated,
        hospitals=hospitals,
    )


def record_to_status_response(record: BatchRecord) -> BulkBatchStatusResponse:
    from .schemas import HospitalRowResponse

    hospitals = [
        HospitalRowResponse(
            row=result.row,
            hospital_id=result.hospital_id,
            name=result.name,
            status=result.status,
            error=result.error,
        )
        for result in record.ordered_results()
    ]
    return BulkBatchStatusResponse(
        batch_id=record.batch_id,
        total_hospitals=record.total_hospitals,
        processed_hospitals=record.processed_hospitals,
        failed_hospitals=record.failed_hospitals,
        processing_time_seconds=record.elapsed_seconds(),
        batch_activated=record.batch_activated,
        hospitals=hospitals,
        status=record.status,
        started_at=record.started_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
        activation_error=record.activation_error,
    )
