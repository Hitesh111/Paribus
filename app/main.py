import asyncio
import logging
from typing import Dict

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import get_settings
from .dependencies import get_bulk_processor
from .exceptions import CSVValidationError
from .parser import parse_hospital_csv
from .processor import BulkHospitalProcessor
from .schemas import BulkBatchStatusResponse, BulkProcessingResponse, CsvValidationResponse

from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Paribus Bulk Processing API...")
    yield


app = FastAPI(
    title="Paribus Hospital Bulk Processing API",
    version="0.1.0",
    description="Bulk CSV ingestion service that creates hospitals through the upstream Hospital Directory API.",
    lifespan=lifespan,
)



def format_validation_error(err: dict) -> str:
    loc = err.get("loc", [])
    msg = err.get("msg", "")
    err_type = err.get("type", "")
    
    if not loc:
        return msg
        
    location = str(loc[0])
    path = " -> ".join(str(x) for x in loc[1:]) if len(loc) > 1 else ""
    
    if err_type == "missing":
        if path:
            return f"Required field '{path}' in {location} is missing."
        return f"Required value in {location} is missing."
    elif err_type.startswith("value_error.extra") or "extra" in err_type:
        if path:
            return f"Extra field '{path}' in {location} is not allowed."
        return f"Extra value in {location} is not allowed."
    elif "type_error" in err_type:
        expected_type = err_type.split(".")[-1]
        if path:
            return f"Field '{path}' in {location} must be a valid {expected_type}."
        return f"Value in {location} must be a valid {expected_type}."
    
    if path:
        return f"Validation error on {location} field '{path}': {msg}."
    return f"Validation error on {location}: {msg}."


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    errors = exc.errors()
    formatted_errors = [format_validation_error(err) for err in errors]
    summary = "Validation failed: " + "; ".join(formatted_errors)
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": summary,
            "error_type": "ValidationError",
            "message": "The request payload failed validation.",
            "errors": [
                {
                    "location": ".".join(str(x) for x in err.get("loc", [])),
                    "message": err.get("msg", ""),
                    "type": err.get("type", ""),
                    "input": err.get("input", None)
                }
                for err in errors
            ]
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error_type": "HTTPException",
            "message": str(exc.detail),
            "status_code": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected error occurred on the server.",
            "error_type": "InternalServerError",
            "message": str(exc),
        }
    )



@app.get("/")
async def root() -> Dict[str, str]:
    return {"message": "Paribus Hospital Bulk Processing API"}


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/hospitals/bulk", response_model=BulkProcessingResponse)
async def bulk_create_hospitals(
    file: UploadFile = File(...),
    processor: BulkHospitalProcessor = Depends(get_bulk_processor),
) -> BulkProcessingResponse:
    content = await file.read()
    try:
        rows = parse_hospital_csv(content, get_settings())
    except CSVValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return await processor.process_new_batch(rows)


@app.get("/hospitals/bulk/{batch_id}", response_model=BulkBatchStatusResponse)
async def get_bulk_status(
    batch_id: str,
    processor: BulkHospitalProcessor = Depends(get_bulk_processor),
) -> BulkBatchStatusResponse:
    try:
        return processor.build_status_response(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Batch {batch_id} was not found.") from exc


@app.post("/hospitals/bulk/{batch_id}/resume", response_model=BulkProcessingResponse)
async def resume_bulk(
    batch_id: str,
    processor: BulkHospitalProcessor = Depends(get_bulk_processor),
) -> BulkProcessingResponse:
    try:
        return await processor.resume_batch(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Batch {batch_id} was not found.") from exc


@app.post("/hospitals/bulk/validate", response_model=CsvValidationResponse)
async def validate_bulk_csv(
    file: UploadFile = File(...),
    processor: BulkHospitalProcessor = Depends(get_bulk_processor),
) -> CsvValidationResponse:
    content = await file.read()
    try:
        return await processor.validate_csv(content)
    except CSVValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@app.websocket("/hospitals/bulk/{batch_id}/ws")
async def bulk_status_ws(
    websocket: WebSocket,
    batch_id: str,
    processor: BulkHospitalProcessor = Depends(get_bulk_processor),
) -> None:
    logger.info(f"WebSocket client requested connection for batch '{batch_id}'")
    await websocket.accept()
    logger.info(f"WebSocket connection accepted for batch '{batch_id}'")
    try:
        while True:
            try:
                batch_status = processor.build_status_response(batch_id)
                await websocket.send_text(batch_status.model_dump_json())
                
                if batch_status.status in {"completed", "activation_failed", "completed_with_failures"}:
                    logger.info(f"Batch '{batch_id}' reached terminal state '{batch_status.status}'. Gracefully closing WS.")
                    break
            except KeyError:
                logger.warning(f"WebSocket requested status for non-existent batch '{batch_id}'")
                await websocket.send_json({"error": f"Batch {batch_id} was not found."})
                break
                
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for batch '{batch_id}'")
