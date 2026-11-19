# Saarthi Architectural & Compliance Invariants

This document codifies the non-negotiable architectural, regulatory, and financial invariants of **Saarthi** (Autonomous AI Debt Resolution Agency & Infrastructure). Any future modifications to backend workflows, agent pipelines, or frontend interfaces MUST strictly satisfy all rules below.

---

## 1. Safety Invariant: LLM Proposes, Deterministic Python Decides
- **LLM Boundary (`sarvam-105b`):** The LLM ONLY extracts unstructured borrower intent, sentiment, numerical offers, and relative date phrases into an `LLMProposal` schema.
- **Deterministic Code Execution:**
  - LLMs are strictly forbidden from calculating calendar dates, interest amounts, waiver approvals, or fee waivers.
  - Python Policy Engine (`agents/policy_engine.py` + `policies/collections_rules.yaml`) computes all ISO dates from live Indian Standard Time (IST).
  - Python enforces the 7-day maximum PTP window (`POLICY-PTP-MAX01`), minimum 30% part-payment threshold (`POLICY-PART-MIN01`), and ₹10,000 shortfall escalation limit.
  - Downstream Action Agent (`agents/action.py`) accepts ONLY a digitally signed, verified `PolicyDecision` object. If `action_permitted == False`, execution is halted immediately.

---

## 2. Zero Real Fund Custody Invariant
- **Direct Lender Escrow Routing:** Saarthi NEVER receives, holds, pools, or transfers borrower money.
- **Lender-Direct UPI VPA:** Every dynamic UPI string (`upi://pay` or `upi://mandate`) routes directly to the lender's authorized escrow VPA (e.g. `repayments.saarthi@yesbank`, `collections.bajaj@hdfcbank`, `dmi.resolve@axisbank`).
- **PNO Disclosure:** Every WhatsApp notification and payment advisory must explicitly disclose the lender's Principal Nodal Grievance Officer name, email, and landline telephone.

---

## 3. Regulatory Invariant: RBI Responsible Business Conduct Directions
- **Calling Hours Window:** Outbound communications are strictly permitted between **08:00 and 19:00 IST**. Outside this window, calls are blocked unless in test/demo override mode.
- **Mandatory 3-Part Opening Disclosure:**
  1. AI Identity Disclosure (`DISC-AI-01`)
  2. Call Recording Notice (`DISC-REC-02`)
  3. Human Opt-Out Mechanism (`DISC-HUMAN-03`): If the borrower says "human", "agent", "अधिकारी", or "माणूस", immediate transfer to a live human representative is triggered.
- **Last-4-Digit Privacy Gate (`RBI-PRIVACY-ID01`):** Zero debt details, overdue amounts, or EMI numbers may be disclosed before verifying the borrower's identity using the last 4 digits of their loan account or Aadhaar.
- **Third-Party Contact Protection (`RBI-PRIVACY-TP02`):** If a third party (spouse, relative, neighbour) answers, zero debt disclosure is permitted and a mandatory 24-hour cooling pause is enforced.
- **6-Month Tamper-Evident Evidence Retention:** Every call transcript, audio telemetry, and policy execution decision must generate a SHA-256 tamper-evident hash stored for a minimum of 6 months.

---

## 4. Root-Cause Downstream Routing Invariant (`POLICY-ROOT-ROUTE01`)
Every dialogue is deterministically classified into one of four root causes:
1. `TEMPORARY_CASHFLOW_MISMATCH`:
   - Triggered by salary delay or shop collection lag.
   - Captured via `POLICY-LIQ-CAPTURE01` (immediate token UPI + weekly Friday AutoPay split) or `POLICY-PREV-FEE01` (T-24h preventive bounce rescue).
   - Once resolved to `PAID`, automatically unlocks **CIBIL Score Protection Active + ₹50,000 Working-Capital Top-Up Pre-Qualified**.
2. `MEDICAL_CALAMITY_SHOCK`:
   - Triggered by hospital, ICU, bereavement, or accident disclosure.
   - Triggers `FAIR-PRAC-SENS01`: immediate 7-day cooling pause, zero payment links to borrower.
   - If `has_hospicash_rider == True`: auto-drafts an **Attached Hospicash / Credit-Shield Claim Packet** (`POLICY-HOSPICASH01`) recovering up to ₹15,000 directly from the designated insurer into the lender's escrow account.
3. `DISPUTE_OR_HARDSHIP`:
   - Triggered by ledger disputes, duplicate debits, or prolonged job loss.
   - Autonomous waiver requests are strictly blocked (`POLICY-WAIVER-NO01`).
   - Case is escalated to the Human Credit Committee / Dispute Resolution Desk.
4. `INTENTIONAL_EVASION`:
   - Triggered by bad-faith refusals or persistent third-party screening. Enforces cooling window before LMS rescheduling.

---

## 5. Offline Safety & Circuit-Breaker Invariant (`SIMULATE=true` Default)
- The system must function completely offline and pass all test suites out-of-the-box without requiring live third-party API credentials (`SIMULATE=true` default).
- When `SIMULATE=false`, all external calls to Sarvam AI (`saaras:v3`, `sarvam-105b`, `bulbul:v3`) must have a strict timeout circuit-breaker (<4.0s) with automatic deterministic fallback so production demos and stage presentations never freeze.
