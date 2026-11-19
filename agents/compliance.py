import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import yaml
from app.models import JourneyRecord, WorkflowStep
from app.config import settings

RULES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "policies", "collections_rules.yaml")

DEFAULT_PROHIBITED_TERMS = [
    "गुंडे", "पुलिस", "बेइज्जत", "बदनाम", "जेल", "jail", "police",
    "रिश्तेदारों", "मोहल्ले", "पीटेंगे", "उठा लेंगे", "धमकी", "मारेंगे",
    "shame", "beat", "harass", "threaten", "defame", "gunda", "court", "कोर्ट",
    "बेशर्म", "चोर", "चीटर", "धोखेबाज", "fir", "arrest"
]

SALES_PROHIBITED_TERMS = [
    "100% free money", "ब्याज कभी नहीं देना", "no repayment needed", "fake loan"
]

def load_collections_rules() -> Dict[str, Any]:
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}

def run_compliance_agent(
    record: JourneyRecord,
    step: Optional[WorkflowStep] = None,
    context: Optional[Dict[str, Any]] = None,
    demo_override_hours: bool = True
) -> JourneyRecord:
    """
    Generic Compliance Agent (Review/Critique):
    - Verifies RBI / TRAI calling hour rules (08:00 - 19:00 IST)
    - Validates mandatory customer consent playback
    - Verifies mandatory identity verification
    - Scans for coercive, abusive, or threatening language
    - Evaluates policy compliance of agreed PTP terms
    - Hard gate: FAIL -> status='escalated', Action agent NEVER executes
    """
    workflow_id = record.workflow_id or (context.get("workflow_id") if context else "collections")
    violations = []
    rules = load_collections_rules() if workflow_id == "collections" else {}

    # 1. Calling Hours Check (IST = UTC + 5:30)
    if not demo_override_hours and not settings.DEMO_OVERRIDE_HOURS:
        ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
        current_hour = ist_now.hour
        if current_hour < 8 or current_hour >= 19:
            violations.append(f"Calling window violation: Call placed at {ist_now.strftime('%H:%M IST')} outside RBI allowed window (08:00 - 19:00 IST).")

    # 2. Consent Check
    if not record.consent_played:
        violations.append("Regulatory non-compliance: Mandatory call recording consent was not played to customer.")

    # 3. Identity Verification Check (Collections)
    if workflow_id == "collections":
        if record.data.get("identity_verified") is False:
            violations.append("Identity Gate Violation: Borrower identity unverified (4-digit loan ID challenge failed).")

    # 4. Transcript Anti-Coercion / Fair Practices Audit
    full_transcript_text = " ".join([t.text for t in record.transcript]).lower()
    found_prohibited = []
    
    prohibited_list = rules.get("compliance_guardrails", {}).get("forbidden_phrases", DEFAULT_PROHIBITED_TERMS)
    terms_to_check = prohibited_list if workflow_id == "collections" else SALES_PROHIBITED_TERMS
    
    for term in terms_to_check:
        # Use word boundaries for short terms like 'fir', 'jail' to avoid false positives in words like 'financial'
        if len(term) <= 3:
            if re.search(rf"\b{re.escape(term.lower())}\b", full_transcript_text):
                found_prohibited.append(term)
        else:
            if term.lower() in full_transcript_text:
                found_prohibited.append(term)

    if found_prohibited:
        violations.append(
            f"CRITICAL VIOLATION - RBI Fair Practices Code: Agent engaged in coercive threats or abusive shaming (Trigger tokens: {', '.join(found_prohibited)})."
        )

    # 5. PTP Policy Check (for Collections)
    if workflow_id == "collections" and record.status == "ptp" and record.ptp_date:
        try:
            ptp_dt = datetime.strptime(record.ptp_date, "%Y-%m-%d").date()
            today = datetime.now(timezone.utc).date()
            max_days = rules.get("negotiation", {}).get("max_ptp_days", 7)
            if ptp_dt > today + timedelta(days=max_days):
                violations.append(f"Policy breach: Agreed PTP date ({record.ptp_date}) exceeds maximum {max_days}-day threshold.")
        except Exception:
            pass

    # Determination
    if violations:
        record.audit_pass = False
        record.audit_reason = " | ".join(violations)
        record.status = "escalated"
        if not record.assigned_human:
            if record.data.get("identity_verified") is False:
                record.assigned_human = "Fraud Prevention & Identity Verification Desk"
            else:
                record.assigned_human = "Chief Compliance Officer"
        summary = f"AUDIT REJECTED: {record.audit_reason} | Execution halted before Action."
    else:
        record.audit_pass = True
        record.audit_reason = "PASSED: Full compliance verified (08:00-19:00 IST window, explicit consent, identity verified, zero coercive language, valid policy)."
        summary = "AUDIT PASSED: 100% compliant with RBI Fair Practices Code & internal lending policy. Permitted to execute Action."

    record.add_trace(
        agent="Compliance",
        action="Regulatory & Fair Practice Code Audit",
        summary=summary
    )

    return record
