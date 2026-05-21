import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from .config import Settings, get_settings
from .exceptions import HospitalDirectoryAPIError
from .models import HospitalCsvRow

logger = logging.getLogger("app")


@dataclass(frozen=True)
class CreatedHospital:
    hospital_id: int
    raw: Dict[str, Any]


class HospitalDirectoryClient:
    def __init__(self, client: httpx.AsyncClient, settings: Optional[Settings] = None) -> None:
        self._client = client
        self._settings = settings or get_settings()

    async def create_hospital(self, row: HospitalCsvRow, batch_id: str) -> CreatedHospital:
        # Developer Test Hook: If the name starts with "FAIL_", artificially simulate an upstream creation error
        if row.name.startswith("FAIL_"):
            raise HospitalDirectoryAPIError(
                action="create hospital",
                message=f"Simulated upstream creation failure for '{row.name}' (Triggered by FAIL_ prefix)",
                status_code=422,
            )

        payload: Dict[str, Any] = {
            "name": row.name,
            "address": row.address,
            "creation_batch_id": batch_id,
            "active": False,
        }
        if row.phone is not None:
            payload["phone"] = row.phone

        max_retries = self._settings.max_retries
        initial_delay = self._settings.initial_retry_delay
        
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"Posting hospital '{row.name}' to upstream API (attempt {attempt + 1}/{max_retries + 1})")
                response = await self._client.post("/hospitals/", json=payload)
                
                if response.status_code >= 400:
                    status_code = response.status_code
                    error_msg = self._extract_error(response)
                    
                    if status_code in {429, 502, 503, 504} and attempt < max_retries:
                        delay = initial_delay * (2 ** attempt)
                        logger.warning(f"Transient error {status_code} for '{row.name}'. Retrying in {delay:.2f}s... (error: {error_msg})")
                        await asyncio.sleep(delay)
                        continue
                        
                    raise HospitalDirectoryAPIError(
                        action="create hospital",
                        message=error_msg,
                        status_code=status_code,
                    )
                    
                data = self._parse_json(response)
                hospital_id = data.get("id", data.get("hospital_id"))
                if hospital_id is None:
                    raise HospitalDirectoryAPIError(
                        action="create hospital",
                        message="The upstream response did not include an id.",
                    )
                return CreatedHospital(hospital_id=int(hospital_id), raw=data)
                
            except (httpx.RequestError, HospitalDirectoryAPIError) as exc:
                should_retry = False
                error_msg = str(exc)
                
                if isinstance(exc, httpx.RequestError) and attempt < max_retries:
                    should_retry = True
                elif isinstance(exc, HospitalDirectoryAPIError) and exc.status_code in {429, 502, 503, 504} and attempt < max_retries:
                    should_retry = True
                    error_msg = exc.message
                
                if should_retry:
                    delay = initial_delay * (2 ** attempt)
                    logger.warning(f"Connection or transient error '{error_msg}' for '{row.name}'. Retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
                    last_exception = exc
                    continue
                else:
                    if isinstance(exc, HospitalDirectoryAPIError):
                        raise
                    raise HospitalDirectoryAPIError(
                        action="create hospital",
                        message=str(exc),
                    ) from exc

        if last_exception:
            if isinstance(last_exception, HospitalDirectoryAPIError):
                raise last_exception
            raise HospitalDirectoryAPIError(
                action="create hospital",
                message=str(last_exception),
            ) from last_exception

    async def activate_batch(self, batch_id: str) -> None:
        max_retries = self._settings.max_retries
        initial_delay = self._settings.initial_retry_delay
        
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"Sending batch activation to upstream API for '{batch_id}' (attempt {attempt + 1}/{max_retries + 1})")
                response = await self._client.patch(f"/hospitals/batch/{batch_id}/activate")
                
                if response.status_code >= 400:
                    status_code = response.status_code
                    error_msg = self._extract_error(response)
                    
                    if status_code in {429, 502, 503, 504} and attempt < max_retries:
                        delay = initial_delay * (2 ** attempt)
                        logger.warning(f"Transient error {status_code} during activation of '{batch_id}'. Retrying in {delay:.2f}s... (error: {error_msg})")
                        await asyncio.sleep(delay)
                        continue
                        
                    raise HospitalDirectoryAPIError(
                        action="activate batch",
                        message=error_msg,
                        status_code=status_code,
                    )
                return
                
            except (httpx.RequestError, HospitalDirectoryAPIError) as exc:
                should_retry = False
                error_msg = str(exc)
                
                if isinstance(exc, httpx.RequestError) and attempt < max_retries:
                    should_retry = True
                elif isinstance(exc, HospitalDirectoryAPIError) and exc.status_code in {429, 502, 503, 504} and attempt < max_retries:
                    should_retry = True
                    error_msg = exc.message
                    
                if should_retry:
                    delay = initial_delay * (2 ** attempt)
                    logger.warning(f"Connection or transient error '{error_msg}' during activation of '{batch_id}'. Retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
                    last_exception = exc
                    continue
                else:
                    if isinstance(exc, HospitalDirectoryAPIError):
                        raise
                    raise HospitalDirectoryAPIError(
                        action="activate batch",
                        message=str(exc),
                    ) from exc

        if last_exception:
            if isinstance(last_exception, HospitalDirectoryAPIError):
                raise last_exception
            raise HospitalDirectoryAPIError(
                action="activate batch",
                message=str(last_exception),
            ) from last_exception

    @staticmethod
    def _parse_json(response: httpx.Response) -> Dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise HospitalDirectoryAPIError(
                action="parse upstream response",
                message="The upstream API did not return valid JSON.",
            ) from exc

        if not isinstance(data, dict):
            raise HospitalDirectoryAPIError(
                action="parse upstream response",
                message="The upstream API returned an unexpected payload.",
            )
        return data

    @classmethod
    def _extract_error(cls, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text.strip() or "Unknown upstream error."

        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("message") or payload.get("error")
            if isinstance(detail, list):
                return json.dumps(detail)
            if detail:
                return str(detail)
        return json.dumps(payload) if payload else "Unknown upstream error."
