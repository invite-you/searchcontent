# Deep Dive 6: Effort and Schedule Estimation

**Unresolved Issue:** Discrepancy in MVP timeline (8-14 weeks vs. 6-9 months).

## 1. Data-Driven Estimation

Based on industry benchmarks for **Enterprise DLP/Security Agents**:
- **DLP Core (Detection + Policy):** 20-30 person-months.
- **Management Console (UI/API/DB):** 30-40 person-months.
- **QA/Productization (MSI/AV Certification):** 10-15 person-months.
- **Total:** ~60-85 person-months.

For a **5-person team**:
- 60 months / 5 people = **12 months (GA Release)**.
- **MVP (Minimal Viable Product):** Typically 50-60% of GA scope = **6-7 months**.

## 2. Recommendation: "The 12-Week Pilot Plan"

Codex's "8-14 weeks" is realistic **only if we define MVP as a 'Pilot'**, not a 'Commercial Product'.

### Phase 0: Validation (Weeks 1-4)
- HWP/PDF extraction success rate.
- NER performance on i3.
- USN Journal driver stability.
- **Outcome:** Kill/Pivot decision.

### Phase 1: Pilot MVP (Weeks 5-16)
- Core Rust Agent (Regex + USN).
- Basic Go Server (Policy + Log receipt).
- Minimal Dashboard (List view).
- **Target:** 100-500 internal test PCs.

### Phase 2: Commercial GA (Months 5-9)
- MSI Packaging, EV Signing.
- Security Audit, Pen-testing.
- Advanced Dashboard (Charts, Workflows).
- **Target:** First paying customer.

## 3. Decision
We adopt **Claude's conservative timeline (6-9 months)** for a saleable product, but use **Codex's aggressive milestones (12 weeks)** for the first working pilot.
- **Budgeting:** Plan for 40-45 person-months for the first year.
