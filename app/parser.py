import csv
import io
from typing import Dict, List, Optional

from .config import Settings
from .exceptions import CSVValidationError
from .models import HospitalCsvRow

ALLOWED_HEADERS = {"name", "address", "phone"}
REQUIRED_HEADERS = {"name", "address"}


def parse_hospital_csv(content: bytes, settings: Settings) -> List[HospitalCsvRow]:
    if not content:
        raise CSVValidationError("The uploaded CSV file is empty.")
    if len(content) > settings.max_upload_bytes:
        raise CSVValidationError(
            f"The uploaded file exceeds the maximum size of {settings.max_upload_bytes} bytes."
        )

    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVValidationError("The CSV file must be UTF-8 encoded.") from exc

    reader = csv.DictReader(io.StringIO(decoded), skipinitialspace=True)
    if reader.fieldnames is None:
        raise CSVValidationError("The CSV file must include a header row.")

    header_map = _normalize_headers(reader.fieldnames)
    missing_headers = REQUIRED_HEADERS - set(header_map)
    if missing_headers:
        missing = ", ".join(sorted(missing_headers))
        raise CSVValidationError(f"The CSV file is missing required headers: {missing}.")

    extra_headers = set(header_map) - ALLOWED_HEADERS
    if extra_headers:
        extra = ", ".join(sorted(extra_headers))
        raise CSVValidationError(f"The CSV file contains unsupported headers: {extra}.")

    rows: List[HospitalCsvRow] = []
    data_row_number = 0
    for row in reader:
        if _is_blank_row(row):
            continue
        if row.get(None):
            raise CSVValidationError(
                f"Row {data_row_number + 1} contains more columns than the header allows."
            )

        data_row_number += 1
        name = _clean_value(row.get(header_map["name"]))
        address = _clean_value(row.get(header_map["address"]))
        phone = None
        if "phone" in header_map:
            phone = _clean_value(row.get(header_map["phone"]))
            if phone == "":
                phone = None

        if not name:
            raise CSVValidationError(f"Row {data_row_number}: 'name' is required.")
        if not address:
            raise CSVValidationError(f"Row {data_row_number}: 'address' is required.")

        rows.append(
            HospitalCsvRow(
                row_number=data_row_number,
                name=name,
                address=address,
                phone=phone,
            )
        )

    if not rows:
        raise CSVValidationError("The CSV file does not contain any hospital rows.")
    if len(rows) > settings.max_batch_size:
        raise CSVValidationError(
            f"The CSV file contains {len(rows)} hospitals, but the maximum allowed is {settings.max_batch_size}."
        )

    return rows


def preview_rows(rows: List[HospitalCsvRow], limit: int = 5) -> List[HospitalCsvRow]:
    return rows[:limit]


def _normalize_headers(headers: List[str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for header in headers:
        if header is None:
            continue
        key = header.strip().lower()
        if not key:
            continue
        if key in normalized:
            raise CSVValidationError(f"Duplicate CSV header detected: {header}.")
        normalized[key] = header
    return normalized


def _is_blank_row(row: Dict[str, str]) -> bool:
    values = list(row.values())
    return not values or all(_clean_value(value) == "" for value in values if value is not None)


def _clean_value(value: Optional[str]) -> str:
    if value is None:
        return ""
    return value.strip()
