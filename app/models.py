from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class HospitalCsvRow:
    row_number: int
    name: str
    address: str
    phone: Optional[str] = None


@dataclass
class RowResult:
    row: int
    name: str
    hospital_id: Optional[int] = None
    status: str = "pending"
    error: Optional[str] = None


@dataclass
class BatchRecord:
    batch_id: str
    rows: Dict[int, HospitalCsvRow]
    results: Dict[int, RowResult] = field(default_factory=dict)
    batch_activated: bool = False
    activation_error: Optional[str] = None
    status: str = "pending"
    started_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    completed_at: Optional[datetime] = None

    @property
    def total_hospitals(self) -> int:
        return len(self.rows)

    @property
    def processed_hospitals(self) -> int:
        return len(self.results)

    @property
    def failed_hospitals(self) -> int:
        return sum(1 for result in self.results.values() if result.status == "failed")

    @property
    def successful_hospitals(self) -> int:
        return sum(1 for result in self.results.values() if result.status in {"created", "created_and_activated"})

    def elapsed_seconds(self, now: Optional[datetime] = None) -> float:
        end_time = now or self.completed_at or utcnow()
        return round((end_time - self.started_at).total_seconds(), 3)

    def ordered_results(self) -> List[RowResult]:
        return [self.results[index] for index in sorted(self.results)]

    def mark_updated(self) -> None:
        self.updated_at = utcnow()

    def mark_processing(self) -> None:
        self.status = "processing"
        self.mark_updated()

    def mark_completed(self, status: str) -> None:
        self.status = status
        self.completed_at = utcnow()
        self.mark_updated()

    def mark_row_success(self, row_number: int, hospital_id: int, activated: bool = False) -> None:
        row = self.rows[row_number]
        self.results[row_number] = RowResult(
            row=row_number,
            name=row.name,
            hospital_id=hospital_id,
            status="created_and_activated" if activated else "created",
        )
        self.mark_updated()

    def mark_row_failure(self, row_number: int, error: str) -> None:
        row = self.rows[row_number]
        self.results[row_number] = RowResult(
            row=row_number,
            name=row.name,
            status="failed",
            error=error,
        )
        self.mark_updated()

    def mark_activation_success(self) -> None:
        self.batch_activated = True
        self.activation_error = None
        for result in self.results.values():
            if result.status == "created":
                result.status = "created_and_activated"
        self.mark_completed("completed")

    def mark_activation_failure(self, error: str) -> None:
        self.batch_activated = False
        self.activation_error = error
        self.mark_completed("activation_failed")

    def mark_completed_with_failures(self) -> None:
        self.batch_activated = False
        self.mark_completed("completed_with_failures")

    def to_processing_status(self) -> str:
        if self.status in {"completed", "completed_with_failures", "activation_failed"}:
            return self.status
        if self.results:
            return "processing"
        return "pending"

