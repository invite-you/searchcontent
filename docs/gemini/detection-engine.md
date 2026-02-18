# Detection Engine Design Specification

**Role:** Detection Architect
**Date:** 2026-02-09
**Status:** Draft

## 1. Executive Summary

This document defines the architecture of the Personal Identifiable Information (PII) detection engine. The primary goal is to achieve **high precision (low false positive rate)** and **low resource consumption (CPU-only)** on standard corporate Windows PCs.

We propose a **Multi-Stage Hybrid Pipeline** that filters candidates progressively:
1.  **Metadata Filter:** Ignored file types.
2.  **Fast Scanner (Regex/Aho-Corasick):** Rapidly identify potential PII candidates.
3.  **Validator (Checksum/Logic):** Validate resident registration numbers (RRNs), credit cards, etc.
4.  **Context Engine (NER - AI):** Use **Quantized KoELECTRA-Small** to analyze the context of unstructured PII (Names, Addresses) and verify ambiguous matches (e.g., distinguishing a phone number from a part number).

---

## 2. Core Constraints & Objectives

*   **Accuracy Target:** Reduce False Positive Rate (FPR) from ~15% (Legacy Regex) to **< 3%**.
*   **Performance:** < 5% CPU usage on average; < 50MB RAM overhead for the model.
*   **Hardware:** No GPU assumption. Must run on Intel Core i3 / 4GB RAM equivalent.
*   **Scope:**
    *   **Structured PII:** Resident Registration Number (RRN), Passport, Driver's License, Credit Card, Phone Number, Email.
    *   **Unstructured PII:** Korean Names, Addresses.

---

## 3. The Pipeline Architecture

The detection process is a funnel. Only highly suspicious data segments reach the expensive AI model.

### Stage 1: File Filtering (Metadata)
*   **Action:** Discard files based on extension, magic number, and size.
*   **Allowlist:** `.txt`, `.csv`, `.xlsx`, `.docx`, `.pptx`, `.hwp`, `.pdf`, `.zip` (extractable).
*   **Blocklist:** System files (`.dll`, `.exe`, `.sys`), Media (`.mp4`, `.jpg` - unless OCR is added later), Logs (`.log` - configurable).
*   **Size Limit:** Max 100MB per file (configurable). Large files are read in chunks.

### Stage 2: Fast Pattern Matching (The "Sieve")
*   **Technology:** `Aho-Corasick` (for keywords) + `Regex` (Rust `regex` crate).
*   **Strategy:**
    *   Use *loose* Regex patterns to catch *all* possibilities (High Recall, Low Precision).
    *   **Keywords:** Trigger scan only if keywords exist (e.g., "이름", "전화번호", "주소", "No.", "Tel").
*   **Output:** List of `Candidate` objects (Start, End, Type, Raw Text).

### Stage 3: Algorithmic Validation (Logic)
*   **Technology:** Pure Rust functions.
*   **Checks:**
    *   **RRN:** Length check (13 digits), Format check (`XXXXXX-XXXXXXX`), Checksum algorithm (Luhn/Verifier).
    *   **Credit Card:** Luhn algorithm, IIN (BIN) range check.
    *   **Email:** Domain validity check (basic TLD).
*   **Decision:**
    *   If invalid checksum -> **DISCARD**.
    *   If valid checksum -> Mark as **HIGH CONFIDENCE** (skip AI) OR **MEDIUM CONFIDENCE** (send to AI depending on type).

### Stage 4: Contextual Analysis (NER - The "Brain")
*   **Target:** Unstructured data (Names, Addresses) and ambiguous Structured data (Phone numbers without labels).
*   **Model:** `monologg/koelectra-small-v3-discriminator` (Fine-tuned for PII).
*   **Inference Engine:** **ONNX Runtime (Microsoft)**.
*   **Optimization:** **Int8 Quantization**.
    *   Model Size: ~14MB (vs 50MB+ FP32).
    *   Inference Time: ~20ms per sentence on CPU.
*   **Logic:**
    *   Extract +/- 50 chars around the `Candidate`.
    *   Run NER.
    *   **Score Boosting:** If Regex found a phone number AND NER tags it as `PHONE` -> **CONFIRMED**.
    *   **False Positive Removal:** If Regex found a phone number BUT NER tags context as "Product Code" or "IP Address" -> **DISCARD**.

---

## 4. NER Model Strategy

### 4.1 Model Selection: KoELECTRA-Small
*   **Why?** BERT is too heavy. DistilBERT has poor Korean support. KoELECTRA-Small offers the best size/performance ratio for Korean.
*   **Labels:** `PER` (Person), `LOC` (Location/Address), `ORG` (Organization), `TEL` (Phone), `ID` (RRN/Passport).

### 4.2 Quantization (CPU Optimization)
We will use **Dynamic Quantization (Int8)**.
*   **Weights:** Stored as 8-bit integers.
*   **Activations:** Quantized on the fly.
*   **Result:** Minimal accuracy loss (<1% F1 score drop) with 2-3x speedup on AVX2-supported CPUs.

### 4.3 Training Data Construction
*   **Source:** AI Hub (modu corpus), In-house generated synthetic PII.
*   **Augmentation:** Heavily augment "False Positive scenarios" (e.g., serial numbers looking like phone numbers, random 13-digit numbers).

---

## 5. False Positive Management (Allowlisting)

Even with AI, errors happen. We need a robust exception system.

*   **Global Allowlist:** Hash (SHA-256) of known benign files.
*   **Pattern Allowlist:** Regex for specific corporate codes (e.g., Employee ID format).
*   **Context Allowlist:** Phrases that ignore detection (e.g., "Example: 010-0000-0000").
*   **Feedback Loop:** User reports "This is not PII" -> Server analyzes -> Updates model/rules.

---

## 6. Performance Budget & Throttling

*   **Process Priority:** `IDLE` or `BELOW_NORMAL`.
*   **Concurrency:** Single-threaded processing for AI inference to avoid freezing the UI.
*   **Throttling:**
    *   Monitor `GetSystemTimes`.
    *   If System CPU > 70%, pause scanning.
    *   Resume when CPU < 50%.

## 7. Future Proofing

*   **OCR Integration:** Tesseract or Windows Media OCR for images (Phase 2).
*   **Custom Models:** Allow larger enterprises to train/finetune their own NER headers.
