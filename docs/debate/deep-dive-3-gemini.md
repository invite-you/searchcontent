# Deep Dive 3: Hardware Fingerprinting Implementation

**Unresolved Issue:** TPM 2.0 vs. Fuzzy Hardware Fingerprinting (WMI-based).

## 1. Technical Analysis

### A. TPM 2.0 Availability
- **Windows 11 Requirement:** TPM 2.0 is mandatory for Win 11.
- **Market Data:** As of 2024, >85% of enterprise-grade PCs (Dell Latitude, HP EliteBook, etc.) shipped after 2018 have TPM 2.0.
- **Windows 10 EOL (Oct 2025):** Most enterprises are currently in a refresh cycle to Win 11, meaning TPM 2.0 penetration will approach 95%+ by the time this product hits GA.

### B. Fuzzy Fingerprinting (WMI) Risks
- **Flakiness:** WMI queries for Disk Serial or Motherboard UUID often return "To Be Filled by O.E.M" or null in VDI (Virtual Desktop) environments.
- **Complexity:** Maintaining a "similarity score" for 50,000 devices is a support nightmare. "Why did my PC block after I changed my RAM?" is a common helpdesk ticket.

## 2. Recommendation: "TPM-First, Machine-ID Fallback"

We should move away from "Fuzzy" logic for licensing and move towards **cryptographic identity**.

### Proposed Hierarchy:
1. **Primary: TPM 2.0 (Non-exportable Key).**
   - Generate a key-pair inside the TPM (KSP). 
   - The private key never leaves the hardware.
   - Sign a challenge from the server. This is 100% unique and tamper-proof.
2. **Fallback: Machine-GUID + OS Disk Serial.**
   - For older legacy PCs (Win 10 without TPM), use a simple combination of `MachineGuid` (from registry) and the physical serial of the OS drive.
   - **No Fuzzy Logic:** If it changes, the device is "New".
3. **Admin Workflow:** 
   - Instead of trying to "guess" if it's the same PC, provide a **"Re-bind"** button in the Management Console.
   - If a user changes hardware, the Admin clicks "Approve Change" which binds the new ID to the existing license seat.

## 3. Benefits
- **Security:** Prevents "License Cloning" where one valid agent's identity is copied to 10 other PCs.
- **Simplicity:** Eliminates the complex "Fuzzy weight" code which is prone to edge-case bugs.
- **Future-Proof:** Aligns with Windows 11 hardware standards.

## 4. Decision for MVP
- Implement **TPM 2.0 binding** as the default.
- Use **Registry MachineGUID** as the fallback for VDI/Legacy.
- **Abandon Fuzzy Fingerprinting** to reduce implementation complexity and support overhead.
