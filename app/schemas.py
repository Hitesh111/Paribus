from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class HospitalRowResponse(BaseModel):
    row: int
    hospital_id: Optional[int] = None
    name: str
    status: str
    error: Optional[str] = None


class BulkProcessingResponse(BaseModel):
    batch_id: str
    total_hospitals: int
    processed_hospitals: int
    failed_hospitals: int
    processing_time_seconds: float = Field(..., ge=0)
    batch_activated: bool
    hospitals: List[HospitalRowResponse]


class BulkBatchStatusResponse(BulkProcessingResponse):
    status: str
    started_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    activation_error: Optional[str] = None


class CsvPreviewRow(BaseModel):
    row: int
    name: str
    address: str
    phone: Optional[str] = None


class CsvValidationResponse(BaseModel):
    valid: bool
    total_hospitals: int
    preview: List[CsvPreviewRow]
    errors: List[str]

