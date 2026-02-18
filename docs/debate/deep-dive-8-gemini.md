# Deep Dive 8: Real-time Detection Timing - Immediate vs. Queued

**Unresolved Issue:** Scan immediately on file change vs. Queue for background processing.

## 1. Technical Analysis

### A. User Experience (The "Jank" Factor)
- **Immediate:** A Minifilter driver intercepts `IRP_MJ_WRITE`. If we scan synchronously, the user's application (Excel, Chrome) freezes until the scan is done. 
- **Risk:** If a file is 50MB, the freeze might last 200-500ms. This is "jank" and leads to "Security solution makes my PC slow" complaints.

### B. Resource Conflict
- When a user saves a file, the OS is busy with I/O.
- If we immediately start a high-CPU NER/Regex scan, we compete for the same I/O and CPU resources at the peak of user activity.

## 2. Recommendation: "Eventual Consistency (Queuing)"

Gemini strongly supports **Codex's Queuing + Resource Governor** approach.

### Proposed Architecture:
1. **Event Capture (Immediate):** 
   - Minifilter driver catches the `Create/Write` event.
   - It pushes the file path to a **Native Lock-free Queue**.
   - It returns control to the user *immediately*.
2. **Resource Governor (The Brain):**
   - A background thread monitors system load (CPU < 10%, User Idle > 5s).
   - When conditions are met, it pops a file from the queue.
3. **Throttling:** 
   - If the queue grows too large (>1,000 items), switch to "Batch Mode" (USN Journal) and discard individual events to save memory.

## 3. Decision
- **Scan Strategy:** **Deferred (Queued) Scanning.**
- **Exceptions:** Only "Blocking" policies (e.g., "Prevent saving PII to USB") require immediate scanning. For general "Audit/Report" policies, 5-10 seconds of delay is perfectly acceptable and preserves the "Quiet Agent" experience.

## 4. Verification (Phase 0)
- Measure the latency of pushing 10,000 paths to a `crossbeam-channel` in Rust. It should be < 1ms.
