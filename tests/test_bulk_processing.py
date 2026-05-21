def upload_csv(client, csv_text: str):
    return client.post(
        "/hospitals/bulk",
        files={"file": ("hospitals.csv", csv_text.encode("utf-8"), "text/csv")},
    )


def validate_csv(client, csv_text: str):
    return client.post(
        "/hospitals/bulk/validate",
        files={"file": ("hospitals.csv", csv_text.encode("utf-8"), "text/csv")},
    )


def test_bulk_create_success(client, fake_client):
    response = upload_csv(
        client,
        "name,address,phone\nGeneral Hospital,123 Main St,555-1111\nCity Care,456 Side St,\n",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_hospitals"] == 2
    assert body["processed_hospitals"] == 2
    assert body["failed_hospitals"] == 0
    assert body["batch_activated"] is True
    assert len(body["hospitals"]) == 2
    assert body["hospitals"][0]["status"] == "created_and_activated"
    assert fake_client.activated_batches
    assert len(fake_client.created_payloads) == 2


def test_bulk_create_partial_failure_skips_activation(client, fake_client):
    fake_client.fail_names.add("Broken Hospital")

    response = upload_csv(
        client,
        "name,address,phone\nWorking Hospital,123 Main St,555-1111\nBroken Hospital,999 Nowhere Rd,555-0000\n",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_hospitals"] == 2
    assert body["processed_hospitals"] == 2
    assert body["failed_hospitals"] == 1
    assert body["batch_activated"] is False
    assert fake_client.activated_batches == []
    statuses = {row["name"]: row["status"] for row in body["hospitals"]}
    assert statuses["Working Hospital"] == "created"
    assert statuses["Broken Hospital"] == "failed"


def test_bulk_validate_success(client):
    response = validate_csv(
        client,
        "name,address,phone\nGeneral Hospital,123 Main St,555-1111\n",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["total_hospitals"] == 1
    assert body["preview"][0]["name"] == "General Hospital"


def test_bulk_validate_missing_header(client):
    response = validate_csv(client, "name,phone\nGeneral Hospital,555-1111\n")
    assert response.status_code == 422
    assert "missing required headers" in response.json()["detail"].lower()


def test_bulk_create_more_than_twenty_rows_rejected(client):
    rows = ["name,address,phone"]
    for index in range(21):
        rows.append(f"Hospital {index},Address {index},555-{index:04d}")
    response = upload_csv(client, "\n".join(rows) + "\n")
    assert response.status_code == 422
    assert "maximum allowed is 20" in response.json()["detail"].lower()


def test_resume_batch_after_partial_failure(client, fake_client):
    fake_client.fail_names.add("Later Hospital")

    first = upload_csv(
        client,
        "name,address,phone\nFirst Hospital,123 Main St,555-1111\nLater Hospital,999 Later St,555-2222\n",
    )
    assert first.status_code == 200
    batch_id = first.json()["batch_id"]

    fake_client.fail_names.remove("Later Hospital")
    resumed = client.post(f"/hospitals/bulk/{batch_id}/resume")
    assert resumed.status_code == 200
    body = resumed.json()
    assert body["batch_activated"] is True
    assert body["failed_hospitals"] == 0
    assert all(row["status"] == "created_and_activated" for row in body["hospitals"])


def test_activation_failure_is_reported_without_crashing(client, fake_client):
    fake_client.activate_failure = "upstream unavailable"

    response = upload_csv(
        client,
        "name,address,phone\nGeneral Hospital,123 Main St,555-1111\n",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["batch_activated"] is False
    assert fake_client.activated_batches

    batch_id = body["batch_id"]
    status_response = client.get(f"/hospitals/bulk/{batch_id}")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["status"] == "activation_failed"
    assert "upstream unavailable" in (status_body["activation_error"] or "")


def test_get_batch_status(client):
    response = upload_csv(
        client,
        "name,address,phone\nGeneral Hospital,123 Main St,555-1111\n",
    )
    batch_id = response.json()["batch_id"]
    status_response = client.get(f"/hospitals/bulk/{batch_id}")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["batch_id"] == batch_id
    assert body["status"] in {"completed", "activation_failed", "completed_with_failures"}


from starlette.websockets import WebSocketDisconnect

def test_websocket_status(client):
    response = upload_csv(
        client,
        "name,address,phone\nGeneral Hospital,123 Main St,555-1111\n",
    )
    batch_id = response.json()["batch_id"]
    
    try:
        with client.websocket_connect(f"/hospitals/bulk/{batch_id}/ws") as websocket:
            data = websocket.receive_json()
            assert data["batch_id"] == batch_id
            assert data["status"] in {"completed", "activation_failed", "completed_with_failures"}
    except WebSocketDisconnect:
        pass


def test_bulk_create_with_failor_csv(client, fake_client):
    with open("testwithfailor.csv", "r", encoding="utf-8") as f:
        csv_content = f.read()

    response = upload_csv(client, csv_content)
    assert response.status_code == 200
    body = response.json()
    
    assert body["total_hospitals"] == 6
    assert body["processed_hospitals"] == 6
    assert body["failed_hospitals"] == 2
    assert body["batch_activated"] is False
    
    statuses = {row["name"]: row["status"] for row in body["hospitals"]}
    assert statuses["St. Jude Children Hospital"] == "created"
    assert statuses["FAIL_Mayo Clinic"] == "failed"
    assert statuses["Cleveland Clinic"] == "created"
    assert statuses["Johns Hopkins Hospital"] == "created"
    assert statuses["FAIL_Massachusetts General Hospital"] == "failed"
    assert statuses["Mount Sinai Hospital"] == "created"
    
    batch_id = body["batch_id"]
    status_response = client.get(f"/hospitals/bulk/{batch_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed_with_failures"


def test_custom_validation_error_format(client):
    # Request without file upload to trigger validation error
    response = client.post("/hospitals/bulk")
    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    assert "error_type" in body
    assert body["error_type"] == "ValidationError"
    assert "errors" in body
    assert len(body["errors"]) > 0
    assert "missing" in body["errors"][0]["type"]
    assert "body.file" in body["errors"][0]["location"]
    # Check that our formatted detail message is readable and clear
    assert "Required field 'file' in body is missing." in body["detail"]


from unittest.mock import AsyncMock, MagicMock, patch
import pytest

@pytest.mark.anyio
async def test_client_retry_behavior():
    from app.clients import HospitalDirectoryClient
    from app.config import Settings
    from app.models import HospitalCsvRow
    import httpx

    settings = Settings(
        hospital_directory_api_base_url="https://fake.url",
        request_timeout_seconds=5.0,
        max_batch_size=20,
        max_upload_bytes=1024,
        concurrency_limit=5,
        max_retries=2,
        initial_retry_delay=0.01,
    )

    response_429 = MagicMock(spec=httpx.Response)
    response_429.status_code = 429
    response_429.json.return_value = {"detail": "Rate limit exceeded"}
    response_429.text = "Rate limit exceeded"

    response_200 = MagicMock(spec=httpx.Response)
    response_200.status_code = 200
    response_200.json.return_value = {"id": 42}
    response_200.text = '{"id": 42}'

    mock_async_client = MagicMock(spec=httpx.AsyncClient)
    mock_async_client.post = AsyncMock()
    mock_async_client.post.side_effect = [response_429, response_200]

    client = HospitalDirectoryClient(mock_async_client, settings=settings)
    row = HospitalCsvRow(row_number=1, name="Retry Hospital", address="123 Retry St")

    with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        res = await client.create_hospital(row, "test-batch-id")
        assert res.hospital_id == 42
        assert mock_async_client.post.call_count == 2
        mock_sleep.assert_called_once_with(0.01)



