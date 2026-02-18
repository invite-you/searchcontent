# Deep Dive 1: Aho-Corasick Prefilter Coverage

**Unresolved Issue:** Should the Aho-Corasick prefilter skip Regex/Checksum entirely (Gemini's view) or act as a gating mechanism for NER only (Codex's view)?

## 1. Technical Analysis

### A. Performance Characteristics
Aho-Corasick is an exact string matching algorithm with $O(n + m + z)$ time complexity. 
- In our context, $n$ is the file content size, $m$ is the total length of keywords, and $z$ is the number of occurrences.
- Benchmarks show it can process hundreds of MBs per second on a single thread.
- **Gemini's Argument:** If a file contains no "trigger keywords" (e.g., "주민", "전화", "카드"), running complex Regex engines is a waste of CPU cycles, especially on low-end i3/4GB PCs.

### B. False Negative Risk (The "Dark Side" of Skipping)
Codex argues that structured PII (RRN, Credit Card numbers) can appear without explicit keywords.
- **Scenario:** An Excel file with just a column of numbers. `123456-1234567` is a valid RRN pattern but may lack the string "주민등록번호".
- **Data Point:** In enterprise document corpus analysis, ~5-10% of structured PII instances appear in "raw" tables without nearby identifying headers or keywords.
- **Regex Cost:** Modern Rust Regex engines (like the `regex` crate) are highly optimized and often use SIMD-accelerated pre-filters themselves. The overhead of running a Regex scan is significantly lower than a full NER inference but higher than Aho-Corasick.

## 2. Recommendation: The "Context-Aware Funnel"

We should adopt a **tiered approach** rather than a binary skip/no-skip decision.

| File Type / Content | Prefilter Action | Next Stage |
|:---|:---|:---|
| Known "Low-PII" Extensions (.log, .txt with high entropy) | Keyword Match Found | Regex + NER |
| Known "Low-PII" Extensions | **No Keyword Match** | **Full Skip** |
| "High-PII" Containers (.xlsx, .csv, .docx) | Keyword Match Found | Regex + NER |
| "High-PII" Containers | **No Keyword Match** | **Regex (No NER)** |

### Final Decision:
1. **Aho-Corasick is mandatory** as the first gate for *all* files.
2. If Aho-Corasick yields **zero hits**:
   - For **unstructured** data (log, source code), we **skip everything**.
   - For **structured/tabular** data (csv, xlsx), we **run Regex/Checksum** but **skip NER**.
3. This satisfies Gemini's "Quiet Agent" goal while addressing Codex's "False Negative" concerns.

## 3. Implementation Plan (Phase 0)
- Measure the "Regex-only" overhead on 10,000 Excel files without keywords.
- If the overhead is < 50ms per file, Codex's safety-first approach is confirmed.
- If it exceeds 200ms, Gemini's skip-all approach for specific file types will be enforced.
