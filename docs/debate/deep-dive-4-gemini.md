# Deep Dive 4: Model File Protection Strategy

**Unresolved Issue:** Disk Encryption (Gemini) vs. Digital Signing (Codex).

## 1. Technical Analysis

### A. Threats to ML Models
1. **Intellectual Property (IP) Theft:** Competitors extracting our KoELECTRA weights to save training costs.
2. **Evasion Attacks:** Attackers modifying the model (e.g., bit-flipping) to ignore specific PII patterns.
3. **Data Poisoning (at Rest):** Replacing the model file with a malicious one that exfiltrates data.

### B. Comparison of Protections
| Feature | Digital Signing (Codex) | Disk Encryption (Gemini) |
|:---|:---|:---|
| **Primary Goal** | Integrity (Anti-Tamper) | Confidentiality (Anti-Theft) |
| **Performance** | Low (Verify at load) | Medium (Decrypt at load) |
| **Implementation** | Easy (Ed25519) | Hard (Key Management) |
| **Bypass** | Hard (Signatures don't lie) | Easy (Memory dump after decryption) |

## 2. Recommendation: "Signed Bundle + Optional Obfuscation"

Confidentiality (Encryption) on an endpoint is a **false sense of security** because the key must reside on the same machine to allow the agent to run. Any motivated attacker can extract the key from the binary or dump the decrypted model from RAM.

### Final Decision:
1. **Mandatory: Digital Signing (Integrity First).**
   - The model and its metadata must be signed by the developer's private key.
   - The agent refuses to load the model if the signature is invalid.
2. **Secondary: "Encryption Lite" (Obfuscation).**
   - Instead of full AES-256 with complex key management, use a **simple XOR/ChaCha20 with a hardware-derived key (TPM/DeviceID)**.
   - This prevents casual copying of the file to another PC (it won't load because the key is different).
   - This satisfies the "IP Protection" requirement for 99% of cases without the "Support Hell" of full disk encryption.
3. **Phase 2:** Consider **ONNX Runtime's Encrypted Custom Loaders** if IP theft becomes a demonstrated business risk.

## 3. Benefits
- **Stability:** Digital signing is extremely robust. If a file is corrupted, we get a clear "Integrity Error" rather than a cryptic "Decryption Failed" crash.
- **Compliance:** Meets "IP protection" checkboxes for enterprise sales.

## 4. Implementation (Phase 1)
- Use `ed25519-dalek` for signature verification.
- Bundle the model, tokenizer, and config into a single `.pii` archive (ZIP/Tar) that is signed as a whole.
