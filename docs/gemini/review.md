# Critical Review & Risk Assessment

**Role:** Devil's Advocate
**Date:** 2026-02-09
**Status:** Review

## 1. The "AI on Endpoint" Fallacy

**Critique:**
The Detection Architect proposes running KoELECTRA (even quantized) on end-user devices.
*   **Risk:** Even 5% CPU usage is noticeable on a dual-core laptop (still common in legacy enterprises). 50,000 PCs means extremely diverse hardware.
*   **Reality Check:** If a developer compiles code, creating 10,000 small object files, and the agent tries to "Intelligently Scan" them, the machine **will** freeze.
*   **Counter-Proposal:** The "Filter" stage must be aggressive.
    *   **Strict Ignore List:** `.obj`, `.class`, `.git`, `node_modules` MUST be ignored by default.
    *   **AI Budget:** Set a hard limit (e.g., max 10 AI inferences per minute). If exceeded, fallback to Regex-only or queue for later.

## 2. Real-time Monitoring Nightmares

**Critique:**
The Systems Architect relies on `ReadDirectoryChangesW`.
*   **Risk:** This API is known to drop events under heavy load (buffer overflow). If the user unzips a 1GB archive with 50k files, the agent will miss half of them or choke trying to catch up.
*   **The USN Trap:** Parsing USN Journals is robust but complex. It requires Admin privileges (which the Service has) but parsing it *correctly* across different NTFS versions is non-trivial.
*   **Verdict:** Do not promise "100% Real-time". Promise "Eventual Consistency". The USN Journal catch-up routine is not just a backup; it's the primary reliability mechanism.

## 3. The 50,000 Certificate Problem

**Critique:**
The Security Engineer suggests mTLS for every agent.
*   **Operational Hell:** Managing, rotating, and revoking 50,000 client certificates is a massive PKI task.
*   **Scenario:** If a cert expires and the auto-renew logic fails (e.g., laptop was off for 3 months), that agent is bricked.
*   **Suggestion:** Use a Hybrid approach.
    *   **Install Time:** Use a "Join Token" (valid for 1 hour) to register.
    *   **Session:** Exchange the Token for a long-lived JWT + Refresh Token.
    *   Reserve mTLS for server-to-server communication only.

## 4. Market Reality vs. Features

**Critique:**
The goal is "Zero False Positives".
*   **Reality:** This is impossible. "010-1234-5678" is a phone number, but it's also a part number in a CSV inventory file. Context helps, but AI is probabilistic.
*   **User Frustration:** If the AI misses a *real* PII because the confidence score was 0.89 (threshold 0.90), the customer will trust the product LESS than a dumb Regex scanner that flags everything.
*   **Advice:** Allow users to tune the "Sensitivity" slider. Don't hide the logic completely inside the black box of AI.

## 5. Final Verdict

The proposed architecture is **Technically Sound but Operationally Optimistic**.

**Required Changes before Approval:**
1.  **Safety Valve:** Implement a "Panic Mode" in the agent. If crash count > 3, disable all hooks and run as a dumb daily scheduler.
2.  **Throttle AI:** AI must be an *opt-in* confirmation step, not the first line of defense for every file.
3.  **Simplify Auth:** Revisit mTLS. Consider standard OIDC/OAuth2 flows with device code grants if possible, or sticking to the proposed JWT scheme without client certs for the endpoint.

**Go/No-Go:** **Conditional Go**. Proceed with prototyping the NER performance on an i3/4GB machine immediately. If inference > 100ms, the entire AI strategy needs a rethink.
