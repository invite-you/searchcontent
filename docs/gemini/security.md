# Security & Licensing Architecture

**Role:** Security Engineer
**Date:** 2026-02-09
**Status:** Draft

## 1. Security Philosophy

> "The PII Scanner must not become a PII Leaker."

The agent processes highly sensitive data. The primary security objective is to ensure that **no actual PII content ever leaves the user's endpoint**, and the agent itself cannot be leveraged as a backdoor.

---

## 2. Threat Modeling

| Threat Actor | Vector | Risk | Mitigation |
| :--- | :--- | :--- | :--- |
| **Malicious Insider** | Sniffing network traffic | Viewing PII reports of others | mTLS, Field Encryption, Minimal Reporting |
| **External Attacker** | Compromising Update Server | Distributing malware to 50k PCs | Code Signing, Hash Verification, Update Manifests |
| **Curious User** | Reverse Engineering | Bypassing license, modifying logic | Binary Obfuscation, Anti-Debugging, Integrity Checks |
| **Malware** | Killing Agent Process | Disabling security audit | Protected Process Light (PPL) - *if feasible*, Watchdog |

---

## 3. Communication Security (Agent <-> Server)

### 3.1 Mutual TLS (mTLS)
We cannot rely on simple API keys.
*   **Protocol:** gRPC over HTTP/2 (TLS 1.3).
*   **Trust:**
    *   **Server Cert:** Validated by Agent via pinned Root CA (not system store).
    *   **Agent Cert:** Unique certificate per organization or machine, issued during installation.
*   **Benefit:** Prevents unauthorized devices from connecting; prevents MITM attacks.

### 3.2 Data Minimization & Privacy
The server stores **metadata only**.
*   **Report Payload Example:**
    ```json
    {
      "file_path": "C:\Users\User\Documents\Resume.docx",
      "risk_level": "High",
      "findings": [
        { "type": "RRN", "count": 1, "mask": "800101-1******" },
        { "type": "PHONE", "count": 2, "mask": "010-****-5678" }
      ]
    }
    ```
*   **Policy:** **NEVER** send the full original text. Masking is done locally on the Agent.

---

## 4. Binary Protection (Anti-Tamper)

### 4.1 Rust-Specific Hardening
*   **String Encryption:** Use `obfstr` crate to encrypt sensitive strings (URLs, Keys, Error messages) at compile time.
*   **Symbol Stripping:** Release builds must use `strip = "symbols"` and `lto = "fat"`.
*   **Panic Handling:** Set `panic = "abort"` to prevent stack unwinding information from leaking structure.

### 4.2 Runtime Integrity
*   **Self-Checksum:** The agent calculates its own hash on startup and compares it against a signed manifest.
*   **Anti-Debugging:**
    *   Periodically check `IsDebuggerPresent` (Win32 API).
    *   Measure execution time of critical blocks (`RDTSC`). If too slow -> assume debugger -> exit or report.
*   **Watchdog:** A separate lightweight service monitors the main detection process. If it dies, it restarts it and logs the event.

---

## 5. Licensing System

We need a flexible subscription model that works **offline**.

### 5.1 License File Format (JWT based)
A JSON Web Token (JWT) signed by the Vendor's Private Key (Ed25519).
*   **Payload:**
    ```json
    {
      "customer_id": "SAMSUNG_ELEC",
      "expiry": "2027-12-31",
      "features": ["ocr", "realtime", "server_report"],
      "max_agents": 50000
    }
    ```

### 5.2 Verification Logic
1.  Agent reads `license.key`.
2.  Verifies signature using embedded Vendor Public Key.
3.  Checks `expiry` date against system time (and secure server time if available).
4.  If invalid: Fallback to "Free Mode" (Local Scan Only, No Reporting) or "Disabled".

### 5.3 Online Activation (Optional but Recommended)
*   To prevent cloning the license file to unauthorized networks, the agent sends a "Heartbeat" with the License ID + Machine ID.
*   Server counts active distinct Machine IDs. If > `max_agents`, flag the license.

---

## 6. Access Control & Logging

*   **Agent UI:** Password protected settings menu to prevent users from disabling the agent.
*   **Audit Logs:** All administrative actions (Stop Service, Change Policy, Exclude File) are logged to the local Event Log and sent to the Server.
