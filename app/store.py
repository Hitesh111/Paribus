import threading
import uuid
from typing import Dict, List, Optional

from .models import BatchRecord, HospitalCsvRow


class BatchStore:
    def __init__(self) -> None:
        # Standard thread lock since FastAPI processes requests in threadpools and our store is in-memory.
        # TODO: If we scale to multiple containers or server pools on Render, we should switch 
        # this in-memory dictionary out for a Redis-backed persistence layer.
        self._lock = threading.Lock()
        self._batches: Dict[str, BatchRecord] = {}


    def create_batch(self, rows: List[HospitalCsvRow]) -> BatchRecord:
        batch_id = str(uuid.uuid4())
        record = BatchRecord(batch_id=batch_id, rows={row.row_number: row for row in rows})
        with self._lock:
            self._batches[batch_id] = record
        return record

    def get_batch(self, batch_id: str) -> Optional[BatchRecord]:
        with self._lock:
            return self._batches.get(batch_id)

    def list_batch_ids(self) -> List[str]:
        with self._lock:
            return list(self._batches.keys())

    def mark_processing(self, batch_id: str) -> BatchRecord:
        with self._lock:
            record = self._require_batch(batch_id)
            record.mark_processing()
            return record

    def mark_row_success(self, batch_id: str, row_number: int, hospital_id: int) -> BatchRecord:
        with self._lock:
            record = self._require_batch(batch_id)
            record.mark_row_success(row_number, hospital_id)
            return record

    def mark_row_failure(self, batch_id: str, row_number: int, error: str) -> BatchRecord:
        with self._lock:
            record = self._require_batch(batch_id)
            record.mark_row_failure(row_number, error)
            return record

    def mark_activation_success(self, batch_id: str) -> BatchRecord:
        with self._lock:
            record = self._require_batch(batch_id)
            record.mark_activation_success()
            return record

    def mark_activation_failure(self, batch_id: str, error: str) -> BatchRecord:
        with self._lock:
            record = self._require_batch(batch_id)
            record.mark_activation_failure(error)
            return record

    def mark_completed_with_failures(self, batch_id: str) -> BatchRecord:
        with self._lock:
            record = self._require_batch(batch_id)
            record.mark_completed_with_failures()
            return record

    def batch_snapshot(self, batch_id: str) -> BatchRecord:
        with self._lock:
            return self._require_batch(batch_id)

    def _require_batch(self, batch_id: str) -> BatchRecord:
        record = self._batches.get(batch_id)
        if record is None:
            raise KeyError(batch_id)
        return record
