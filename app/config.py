from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True)
class Settings:
    hospital_directory_api_base_url: str
    request_timeout_seconds: float
    max_batch_size: int
    max_upload_bytes: int
    concurrency_limit: int
    max_retries: int
    initial_retry_delay: float


@lru_cache()
def get_settings() -> Settings:
    return Settings(
        hospital_directory_api_base_url=os.getenv(
            "HOSPITAL_DIRECTORY_API_BASE_URL",
            "https://hospital-directory.onrender.com",
        ).rstrip("/"),
        request_timeout_seconds=float(os.getenv("HOSPITAL_DIRECTORY_TIMEOUT_SECONDS", "15")),
        max_batch_size=int(os.getenv("MAX_BULK_HOSPITALS", "20")),
        max_upload_bytes=int(os.getenv("MAX_BULK_UPLOAD_BYTES", "1048576")),
        concurrency_limit=int(os.getenv("HOSPITAL_DIRECTORY_MAX_CONCURRENCY", "5")),
        max_retries=int(os.getenv("HOSPITAL_DIRECTORY_MAX_RETRIES", "3")),
        initial_retry_delay=float(os.getenv("HOSPITAL_DIRECTORY_INITIAL_RETRY_DELAY", "1.0")),
    )

