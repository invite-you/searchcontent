# Deep Dive 5: Technology Stack - C#/.NET Exclusion

**Unresolved Issue:** Should we strictly use Rust for the agent (Gemini/Claude) or allow C#/.NET for specific components (Codex's exception)?

## 1. Technical Analysis

### A. The "Size & Performance" Cost
- **Native AOT (C#):** Recent .NET 8/9 AOT can produce executables around **5-8MB**. However, once you include UI libraries or complex interop, this grows.
- **Memory (RSS):** A C# AOT process still carries the .NET Runtime's garbage collector (GC). Minimum RSS is typically **20-30MB**.
- **Rust:** A comparable Rust agent starts at **2-3MB** RSS.

### B. Interop Overhead (FFI vs. P/Invoke)
- Interop between a C# Service and a Rust Worker (via IPC/Named Pipes) introduces **serialization latency**.
- Managing two separate toolchains (Cargo + dotnet), two dependency trees, and two sets of security vulnerabilities doubles the maintenance burden.

## 2. Recommendation: "Strict Rust Principle"

We must stick to **Pure Rust** for the agent.

### Why?
1. **Atomic Deployment:** A single static binary with zero dependencies is the "holy grail" for enterprise deployment (50,000 PCs). No ".NET Framework 4.8 required" or "Install Desktop Runtime" popups.
2. **Predictability:** In 4GB RAM environments, C#'s GC spikes can trigger the "Panic Mode" of our agent unnecessarily.
3. **The "DRM/COM" Argument:** Codex argued that C# is better for Windows COM/DRM. While true, Rust's `windows` crate (by Microsoft) is now mature enough to handle COM/Win32 API calls effectively.

### Exception Policy:
- If a specific **Third-party DRM SDK** is *only* provided as a .NET DLL (highly unlikely for low-level DRM), we will wrap it in a **separate worker process** using C# AOT, keeping the core agent pure Rust.

## 3. Decision
- **Core Agent:** 100% Rust.
- **Server:** 100% Go.
- **Management Console:** React/TypeScript.
- **Rationale:** Minimize the "Language Matrix". 3 languages (Rust, Go, TS) is the limit for a 5-person team. Adding C# is a liability, not an asset.
