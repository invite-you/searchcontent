# Deep Dive 2: NER Model Load/Unload Strategy

**Unresolved Issue:** Should the NER model be resident in memory (Resident) or loaded per scan session (Session-based)?

## 1. Technical Analysis

### A. Loading Latency
Our target model is **KoELECTRA-Small v3 (INT8 quantized)**, approximately **14-18MB** including the tokenizer.
- **ONNX Runtime Loading Benchmarks:** Loading a <20MB model from an SSD typically takes **150ms - 400ms**. On a fragmented HDD (older enterprise PCs), this can spike to **1.5s - 2.0s**.
- **Tokenizer Overhead:** Loading the vocabulary and initializing the Rust `tokenizers` crate takes an additional **50ms - 100ms**.

### B. Memory Constraints
Target Environment: **Intel i3 / 4GB RAM**.
- A resident model + ONNX Runtime engine (shared libraries) will occupy roughly **40-60MB** of RSS (Resident Set Size).
- In a 4GB system, 60MB is ~1.5% of total RAM. While small, multiple "resident" security agents (AV, EDR, DLP) often lead to "RAM creep" and system slowdown.

## 2. Recommendation: "Session-Based with Debounce"

Gemini supports Claude's "Session-based" approach with a modification for real-time events.

### Proposed Strategy:
1. **Scheduled Scan:** Load at start of scan, unload at end. The 500ms load time is negligible compared to a 1-hour scan.
2. **Real-time Event (Watchdog):**
   - **Debounce Window (30-60s):** When a file change is detected, wait 30 seconds for more events.
   - **Lazy Load:** If events exist in the queue, load the model, process the batch, and keep it in memory.
   - **Idle Timeout (5 min):** If no new NER requests arrive for 5 minutes, **unload** the model to free the 60MB RSS.

## 3. Benefits
- **Zero Idle Impact:** When the PC is just being used for browsing/mail, the 0MB overhead fulfills the "Quiet Agent" promise.
- **Performance:** For high-activity periods (e.g., downloading a zip of 100 files), the debounce/batching ensures we only pay the "loading tax" once.

## 4. Verification Plan (Phase 0)
- Measure `ort` (ONNX Runtime) session creation time on a VM limited to 1 CPU core and 2GB RAM.
- Verify if `Unload` actually releases all memory back to the OS (monitoring for memory leaks in the FFI boundary).
