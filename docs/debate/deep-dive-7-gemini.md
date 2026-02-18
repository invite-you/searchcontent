# Deep Dive 7: Rule Definition Format - JSON vs. Code

**Unresolved Issue:** Should rules be hardcoded in Rust (Claude) or defined in a schema-based format (Codex)?

## 1. Technical Analysis

### A. Flexibility vs. Performance
- **Hardcoded:** Compiled into the binary. Zero parsing overhead. Safest against tampering. **Weakness:** Requires a full binary update to add a new "Credit Card" pattern.
- **JSON/YAML:** Parsed at runtime. Allows "Hot Updates" (updating rules without restarting the agent). **Weakness:** Parsing overhead (negligible for <100 rules), schema validation complexity.

### B. Industry Standard
- Every major security product (Snort, YARA, Defender, CrowdStrike) uses a **declarative format** (Rules, Signatures).
- Hardcoding rules is a "Startup Debt" that will cause friction as soon as the first customer asks for a "Custom 사내 사번 pattern".

## 2. Recommendation: "Typed JSON with Internal DSL"

We should follow Codex's advice but keep it extremely simple to avoid Claude's "Mini-language" concern.

### Proposed Format (JSON):
```json
{
  "rule_id": "kr_rrn",
  "name": "주민등록번호",
  "type": "regex",
  "pattern": "\d{6}-[1-4]\d{6}",
  "checksum": "luhn_mod11",
  "keywords": ["주민", "번호", "생년월일"]
}
```

### Constraints:
1. **No Logic in JSON:** No `if/else`, no loops. Only declarative data.
2. **Strict Schema:** Use `serde` in Rust to deserialize into a fixed `struct`.
3. **Signed Bundle:** Rules are NOT edited as raw files on the disk. They are downloaded as a **Signed JSON Bundle**.

## 3. Decision
- **MVP:** Use **JSON** for rule definitions.
- **Rationale:** The logic for "Regex + Checksum + Keywords" is static. Only the *parameters* (the regex string, the list of keywords) change. This allows us to push a 1KB JSON update to 50,000 PCs in minutes, rather than pushing a 10MB binary.
