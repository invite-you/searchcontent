# System Architecture Specification

**Role:** Systems Architect
**Date:** 2026-02-09
**Status:** Draft

## 1. High-Level Architecture

The system follows a classic **Hub-and-Spoke** model.
*   **Nodes (50,000+):** Windows PC Agents (Rust).
*   **Hub:** Central Management Server (On-Premise or Cloud).

```mermaid
graph TD
    A[PC Agent 1] -->|gRPC/TLS| LB[Load Balancer]
    B[PC Agent 2] -->|gRPC/TLS| LB
    C[PC Agent N] -->|gRPC/TLS| LB
    LB --> API[API Server Cluster]
    API --> MQ[Message Queue (Kafka)]
    MQ --> Worker[Log Processor]
    Worker --> DB[(PostgreSQL)]
    Worker --> ES[(Elasticsearch)]
    Dashboard[Web Console] --> API
```

---

## 2. Client Architecture (Windows Agent)

To ensure stability and UI separation, the agent is split into two components.

### 2.1 Component Diagram
1.  **Core Service (`pii-service.exe`):**
    *   **Type:** Windows Service.
    *   **Privilege:** `LOCAL SYSTEM`.
    *   **Role:** File monitoring, Scanning, API communication, Enforcement.
    *   **Language:** Rust.
2.  **User Interface (`pii-tray.exe`):**
    *   **Type:** Desktop Application (Tray Icon).
    *   **Privilege:** User Level.
    *   **Role:** Notifications (Toast), Scan Progress, On-Demand Scan trigger.
    *   **Tech:** Rust (Tauri) or native Windows API.
3.  **IPC:** Named Pipes (`\.\pipe\pii_agent_comm`) for communication between Service and UI.

### 2.2 File System Monitoring Strategy
*   **Real-time:** Use `ReadDirectoryChangesW` (via `notify` crate).
    *   *Debouncing:* Wait 2-5 seconds after a `Write` event to ensure file save is complete before scanning.
*   **Offline/Missed Events:** Use **USN Journal**.
    *   On startup, check the USN Journal cursor.
    *   Scan all files modified since the last cursor position.
*   **Full Scan:** Low-priority background thread that iterates through all fixed drives.

### 2.3 Resource Management (The "Nice" Agent)
*   **CPU Limit:** Hard cap at 1 core usage logic (sleeps if processing logic takes too long).
*   **IO Limit:** Small read buffer (e.g., 4KB-16KB chunks) to prevent disk thrashing.
*   **Battery Mode:** If running on laptop battery, increase scan intervals or pause background scanning.

---

## 3. Server Architecture

Handling 50,000 concurrent connections requires an asynchronous, event-driven backend.

### 3.1 Tech Stack
*   **Language:** Go (Golang) or Rust. (Go is chosen for faster development speed of standard web APIs).
*   **Protocol:** gRPC (Protobuf) for performance and strong typing.
*   **Database:**
    *   **PostgreSQL:** Tenants, Policies, Agent Status, Aggregated Stats.
    *   **Elasticsearch (or OpenSearch):** Searchable index of individual detection logs.
*   **Queue:** Apache Kafka or NATS JetStream. Decouples ingestion from processing.

### 3.2 Scalability Strategy
*   **Stateless API:** The API servers hold no state. Can scale horizontally behind Nginx/HAProxy.
*   **Batch Ingestion:** Agents buffer logs locally and upload in batches (e.g., every 10 mins or when 50 logs accumulate) to reduce HTTP overhead.
*   **Partitioning:** Database partitioned by `OrganizationID` or `Time` (for logs).

---

## 4. Deployment & Updates

### 4.1 Installation
*   **Format:** MSI (Microsoft Installer).
*   **Distribution:** Active Directory GPO, SCCM, or MDM (Intune).
*   **Silent Install:** `msiexec /i pii-agent.msi /qn KEY="LICENSE_KEY" SERVER="https://api.company.com"`

### 4.2 Auto-Update System
*   **Mechanism:** Two-partition update (A/B) or simple binary replacement.
*   **Process:**
    1.  Agent queries `GetVersion` API.
    2.  If new version available, download signed binary to `C:\ProgramData\...\Updates`.
    3.  Verify Signature.
    4.  Service stops itself -> Moves new binary -> Restarts.
    5.  **Rollback:** If Service fails to start 3 times, revert to backup binary.

---

## 5. Data Flow Summary
1.  **File Change** -> **Notify Event** -> **Queue**.
2.  **Worker Thread** -> **Pipeline (Regex -> NER)** -> **Result**.
3.  **Result** -> **Local DB (SQLite/Sled)** -> **Batch Uploader**.
4.  **Batch Uploader** -> **gRPC Server** -> **Kafka**.
5.  **Kafka Consumer** -> **Elasticsearch** -> **Admin Dashboard**.
