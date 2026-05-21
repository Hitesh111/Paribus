# Paribus API Scenarios & Decision Trees

This document maps out every possible system execution path, request flow, validation rule, error boundary, and recovery state for the Paribus Bulk Processing Service. It shows exactly how your local service coordinates with the upstream Hospital Directory API.

---

## 1. Global API Workflow Decision Tree

The following diagram illustrates the lifecycle of a CSV upload request, tracing its progression through validation, concurrent creation, and upstream batch activation.

```mermaid
graph TD
    A[Client uploads CSV file] --> B{POST /hospitals/bulk/validate}
    B -->|CSV invalid| C[Return 422 Unprocessable Content]
    B -->|CSV valid| D[Generate Unique UUID Batch ID]
    
    D --> E[Start Concurrent Uploads to Upstream API]
    E --> F{Do all N rows succeed?}
    
    F -->|No: M rows fail| G[Skip Batch Activation]
    G --> H[Mark Status: completed_with_failures]
    H --> I[Return batch status with row failures]
    
    F -->|Yes: All rows created| J[Call Upstream: PATCH /activate]
    J -->|Activation succeeds| K[Mark Status: completed]
    K --> L[Return batch status: active & completed]
    
    J -->|Activation fails| M[Mark Status: activation_failed]
    M --> N[Return status with activation error details]
```

---

## 2. In-Depth Scenario Breakdown

### Scenario 1: CSV Syntax & Schema Validation
* **Endpoint:** `POST /hospitals/bulk/validate` or standard upload at `POST /hospitals/bulk`
* **Workflow:** parses the file in memory without hitting any external resources.

| Input Scenario | Expected Outcome | HTTP Status | Response Payload Example |
| :--- | :--- | :--- | :--- |
| **Empty File** | Rejection | `422` | `{"detail": "The uploaded CSV file is empty."}` |
| **File too large (>1MB)** | Rejection | `422` | `{"detail": "The uploaded file exceeds the maximum size of 1048576 bytes."}` |
| **Missing required headers** (e.g. `address` missing) | Rejection | `422` | `{"detail": "The CSV file is missing required headers: address."}` |
| **Unsupported headers** (e.g. `fax_number` present) | Rejection | `422` | `{"detail": "The CSV file contains unsupported headers: fax_number."}` |
| **Duplicate headers** (e.g. `name,name,address`) | Rejection | `422` | `{"detail": "Duplicate CSV header detected: name."}` |
| **Row count exceeds limit (>20)** | Rejection | `422` | `{"detail": "The CSV file contains 25 hospitals, but the maximum allowed is 20."}` |
| **Empty name/address values on row** | Rejection | `422` | `{"detail": "Row 2: 'name' is required."}` |
| **Valid CSV** | Success | `200` | `{"valid": true, "total_hospitals": 3, "preview": [...], "errors": []}` |

---

### Scenario 2: Processing and Concurrency (`POST /hospitals/bulk`)
* **Endpoint:** `POST /hospitals/bulk`
* **Trigger:** A structurally valid CSV is received.

```mermaid
graph TD
    Start[CSV Validated] --> Gen[Gen Batch ID: uuid]
    Gen --> Store[Create In-Memory Batch Record]
    
    subgraph "Concurrent Workers (asyncio.gather)"
        Store --> W1[POST /hospitals/ Row 1]
        Store --> W2[POST /hospitals/ Row 2]
        Store --> W3[POST /hospitals/ Row N]
    end
    
    W1 -->|Success| R1[Mark Row 1: created]
    W1 -->|Fail| RF1[Mark Row 1: failed]
    
    W2 -->|Success| R2[Mark Row 2: created]
    W3 -->|Success| R3[Mark Row N: created]
```

#### Decision Logic Post-Ingestion:
1. **Case A: 100% Row Success:**
   * Trigger upstream patch: `PATCH /hospitals/batch/{batch_id}/activate`
   * **If activation succeeds:** Set status to `completed` and mark all rows `created_and_activated`.
   * **If activation fails:** Set status to `activation_failed` (retains local success records, but marked inactive).
2. **Case B: Partial/Total Row Failure:**
   * **Skip Activation** immediately (keeps successful records safely isolated as inactive in upstream db).
   * Set status to `completed_with_failures` (contains exact failure diagnostics per row).

---

### Scenario 3: Resuming Operations (`POST /hospitals/bulk/{batch_id}/resume`)
* **Endpoint:** `POST /hospitals/bulk/{batch_id}/resume`
* **Trigger:** The client requests recovery of a previously failed batch.

```mermaid
graph TD
    Start[Receive Resume Request] --> Check{Check current Batch State}
    
    Check -->|Already fully completed & active| Success[Do nothing, return current status]
    
    Check -->|All rows created, but activation had failed| ActOnly[Call Upstream: PATCH /activate]
    ActOnly -->|Activation succeeds| ActS[Mark Status: completed]
    ActOnly -->|Activation fails| ActF[Status remains: activation_failed]
    
    Check -->|Some rows failed during initial creation| RetryRows[Identify failed rows and retry concurrent creation]
    RetryRows -->|Some retried rows fail again| FailS[Status remains: completed_with_failures]
    RetryRows -->|All retries succeed now| ActAll[Call Upstream: PATCH /activate]
    
    ActAll -->|Succeeds| FinS[Mark Status: completed]
    ActAll -->|Fails| FinF[Mark Status: activation_failed]
```

---

### Scenario 4: Real-time Client Streaming (`WS /hospitals/bulk/{batch_id}/ws`)
* **Endpoint:** `/hospitals/bulk/{batch_id}/ws`
* **Trigger:** The client opens a WebSocket connection to monitor execution real-time.

```mermaid
sequenceDiagram
    participant Client
    participant WebSocket Handler
    participant Batch Store
 
    Client->>WebSocket Handler: Establish WebSocket Connection
    WebSocket Handler->>WebSocket Handler: Accept connection
    
    loop Every 0.5 Seconds (until terminal state reached)
        WebSocket Handler->>Batch Store: Retrieve Batch snapshot
        Batch Store-->>WebSocket Handler: Current state (total, processed, status, failures)
        WebSocket Handler->>Client: Send JSON update (BulkBatchStatusResponse)
        
        opt Terminal State Reached (completed, activation_failed, completed_with_failures)
            WebSocket Handler->>WebSocket Handler: Break loop
            WebSocket Handler->>Client: Close WebSocket gracefully
        end
    end
```

---

## 3. Concurrency, Thread-Safety & Memory Queue Model

Here is a high-resolution, premium visual diagram detailing the asynchronous execution flow, thread locking, and event queue:

![Asynchronous Concurrency Architecture Diagram](docs/assets/concurrency_decision_tree.png)

The diagram below details the step-by-step decision and execution flow when a request enters the application, showing how thread-locks, async micro-tasks, and the in-memory state dict coordinate.

```mermaid
flowchart TD
    Req[POST /hospitals/bulk Uploaded] --> Parse{Parser Validates CSV}
    
    Parse -->|Invalid| Err[Abort with 422 Exception]
    Parse -->|Valid| Init[Generate UUID Batch ID]
    
    Init --> Lock1[Acquire Thread Lock]
    Lock1 --> WriteMem[Create Batch Record in Dict]
    WriteMem --> Unlock1[Release Thread Lock]
    
    Unlock1 --> Spawn[Register N Coroutines on Asyncio Event Loop]
    
    subgraph "Single-Threaded Event Loop (Non-Blocking Concurrency)"
        Spawn --> Loop[asyncio.gather]
        Loop --> Row1[process_row 1]
        Loop --> Row2[process_row 2]
        Loop --> RowN[process_row N]
    end
    
    subgraph "Individual Row Execution"
        Row1 --> HitAPI1{HTTP Call Upstream}
        HitAPI1 -->|Succeeds| L_S[Acquire Lock & Mark row success]
        HitAPI1 -->|Fails| L_F[Acquire Lock & Mark row failure]
    end
    
    subgraph "WebSocket Polling Loop (Parallel Client Request)"
        WS[WebSocket Client connected] --> WS_Loop[Sleep 0.5s]
        WS_Loop --> WS_Lock[Acquire Lock & Read current progress]
        WS_Lock --> WS_Send[Send Progress Status]
        WS_Send --> WS_Loop
    end
    
    L_S --> Gather[Wait for asyncio.gather to finish]
    L_F --> Gather
    
    Gather --> CheckFail{Were there any row failures?}
    
    CheckFail -->|Yes| SkipAct[Skip Activation step]
    SkipAct --> LockFail[Acquire Lock & Set status: completed_with_failures]
    LockFail --> Resp1[Return HTTP 200 JSON Response]
    
    CheckFail -->|No| ActUp[Call Upstream Activation PATCH /activate]
    ActUp -->|Activation succeeds| LockSucc[Acquire Lock & Set status: completed]
    LockSucc --> Resp2[Return HTTP 200 JSON Response]
    
    ActUp -->|Activation fails| LockActFail[Acquire Lock & Set status: activation_failed]
    LockActFail --> Resp3[Return HTTP 200 JSON Response]
```

