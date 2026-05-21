# 🏢 Paribus Hospital Bulk Ingestion System

An enterprise-grade, high-performance, and resilient FastAPI bulk ingestion service. It processes multipart CSV hospital rosters, performs structural/schema validations, manages concurrent upstream dispatching with adaptive throttling, and handles atomic batch activations.

---

## 🚀 Quick Links
* **Live API Endpoint:** [https://paribus-hospital-bulk-processing.onrender.com](https://paribus-hospital-bulk-processing.onrender.com)
* **Interactive API Documentation (Swagger):** [https://paribus-hospital-bulk-processing.onrender.com/docs](https://paribus-hospital-bulk-processing.onrender.com/docs)
* **API Flow Details:** [api_scenarios_decision_tree.md](./api_scenarios_decision_tree.md)

---

## ✨ Upstream Resilience & Reliability
This system is engineered to handle fragile or rate-limited upstream services with modern asynchronous patterns:
1. **Adaptive Throttling (Concurrency Gate)**: Limits parallel requests to the upstream directory service to `5` concurrent connections (using an `asyncio.Semaphore`) to avoid rate limits.
2. **Exponential Backoff Retries**: Automatically retries transient status codes (`429`, `502`, `503`, `504`) and connection drops (`httpx.RequestError`) with an exponential delay.
3. **Structured Application Logging**: Provides contextual logs of asynchronous tasks, retry attempts, and batch progression.
4. **Modern FastAPI Lifespan Handling**: Replaced all deprecated `@app.on_event("startup")` hooks with modern, clean context managers.

---

## ⚡ Quickstart Guide

### 1. Run Locally
Get the application up and running locally in seconds using our automated scripts:
```bash
# Setup the virtual environment and install all packages
./setup.sh

# Start the local development server (runs on port 8080)
./run.sh
```
The API will be available locally at [http://localhost:8080](http://localhost:8080).

### 2. Run with Docker Compose
```bash
docker compose up --build
```

---

## 🧪 Testing

We provide robust, one-step test commands:

* **Run Local Pytest Suite** (displays beautiful status indicators):
  ```bash
  ./runtest.sh
  ```
* **Run Live Integration Tests** (executes against the deployed Render app):
  ```bash
  python test_live.py
  ```

---

## 📡 API Endpoints

### Ingestion & Validation

* `POST /hospitals/bulk` - Uploads a multipart CSV roster and starts concurrent upstream ingestion.
* `POST /hospitals/bulk/validate` - Validates the CSV format, columns, size, and rows in-memory without processing it.

### Polling & Syncing

* `GET /hospitals/bulk/{batch_id}` - Polls the real-time execution progress of a specific batch.
* `POST /hospitals/bulk/{batch_id}/resume` - Resumes a failed batch, retrying only the failed rows or activation step.
* `WS /hospitals/bulk/{batch_id}/ws` - Established a WebSocket connection to stream live status updates every `0.5s` until complete.

### System Health
* `GET /health` - Light check returning `{"status": "ok"}`.

---

## 📝 CSV Format
The pipeline accepts `.csv` files up to **1MB** and **20 records** per batch:
* **Required Headers**: `name`, `address`
* **Optional Header**: `phone`
