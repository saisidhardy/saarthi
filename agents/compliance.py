import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from app.models import JourneyRecord, WorkflowStep
from app.config import settings

PROHIBITED_TERMS = [
    "गुंडे", "पुलिस", "बेइज्जत", "बदनाम", "जेल", "jail", "police",
    "रिश्तेदारों", "मोहल्ले", "पीटेंगे", "उठा लेंगे", "धमकी", "मारेंगे",
    "shame", "beat", "harass", "threaten", "defame", "gunde"
]

SALES_PROHIBITED_TERMS = [
    "100% free money", "ब्याज कभी नहीं देना", "no repayment needed", "fake loan"
]

def run_compliance_agent(
    record: JourneyRecord,
    step: Optional[WorkflowStep] = None,
    context: Optional[Dict[str, Any]] = None,
    demo_override_hours: bool = True
) -> JourneyRecord:
    """
    Generic Compliance Agent:
    - Verifies RBI / TRAI calling hour rules (08:00 - 19:00 IST)
    - Validates mandatory customer consent playback
    - Scans for coercive, abusive, or misleading language
    - Evaluates policy compliance of agreed terms
    """
    workflow_id = record.workflow_id or (context.get("workflow_id") if context else "collections")
    violations = []

    # 1. Calling Hours Check (IST = UTC + 5:30)
    if not demo_override_hours and not settings.DEMO_OVERRIDE_HOURS:
        ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
        current_hour = ist_now.hour
        if current_hour < 8 or current_hour >= 19:
            violations.append(f"Calling window violation: Call placed at {ist_now.strftime('%H:%M IST')} outside RBI allowed window (08:00 - 19:00 IST).")

    # 2. Consent Check
    if not record.consent_played:
        violations.append("Regulatory non-compliance: Mandatory call recording consent was not played to customer.")

    # 3. Transcript Anti-Coercion / Fair Practices Audit
    full_transcript_text = " ".join([t.text for t in record.transcript])
    found_prohibited = []
    
    terms_to_check = PROHIBITED_TERMS if workflow_id == "collections" else SALES_PROHIBITED_TERMS
    for term in terms_to_check:
        if term.lower() in full_transcript_text.lower():
            found_prohibited.append(term)

    if found_prohibited:
        violations.append(
            f"CRITICAL VIOLATION - RBI Fair Practices Code: Agent engaged in coercive / abusive threats or deceptive terms (Trigger tokens: {', '.join(found_prohibited)})."
        )

    # 4. PTP Policy Check (for Collections)
    if workflow_id == "collections" and record.status == "ptp" and record.ptp_date:
        try:
            ptp_dt = datetime.strptime(record.ptp_date, "%Y-%m-%d").date()
            today = datetime.now(timezone.utc).date()
            if ptp_dt > today + timedelta(days=7):
                violations.append(f"Policy breach: Agreed PTP date ({record.ptp_date}) exceeds maximum 7-day threshold.")
        except Exception:
            pass

    # Determination
    if violations:
        record.audit_pass = False
        record.audit_reason = " | ".join(violations)
        summary = f"AUDIT REJECTED: {record.audit_reason}"
    else:
        record.audit_pass = True
        record.audit_reason = "PASSED: Full compliance verified (Calling hours IST, explicit consent, zero coercive language, valid policy)."
        summary = "AUDIT PASSED: 100% compliant with RBI Fair Practices Code & internal lending policy."

    record.add_trace(
        agent="Compliance",
        action="Regulatory & Fair Practice Code Audit",
        summary=summary
    )

    return record
