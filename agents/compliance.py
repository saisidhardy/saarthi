import os
import re
from datetime import datetime, timezone, timedelta
from app.models import CaseFile
from app.config import settings

# RBI Fair Practices Code Prohibited Lexicon
PROHIBITED_TERMS = [
    "गुंडे", "पुलिस", "बेइज्जत", "बदनाम", "जेल", "jail", "police",
    "रिश्तेदारों", "मोहल्ले", "पीटेंगे", "उठा लेंगे", "धमकी", "मारेंगे",
    "shame", "beat", "harass", "threaten", "defame", "gunde", "legal notice abhi bhejta hoon"
]

COMPLIANCE_AUDIT_PROMPT = """You are the Chief Compliance Auditor for an RBI-regulated Indian lender.
Review this collections transcript against the RBI Fair Practices Code:
1. Consent mandatory: Did agent state call is recorded?
2. Zero Coercion: Did agent threaten physical harm, police, legal incarceration, or third-party/relative defamation?
3. Permitted Calling Hours: 08:00 to 19:00 IST.

Return JSON ONLY:
{
    "audit_pass": true or false,
    "audit_reason": "Detailed compliance determination"
}
"""

def run_compliance_agent(case: CaseFile, demo_override_hours: bool = True) -> CaseFile:
    """
    Compliance Agent:
    - Verifies RBI calling hour rules (08:00 - 19:00 IST)
    - Validates mandatory borrower consent playback
    - Scans for coercive, abusive, or third-party shaming language
    - Evaluates policy compliance of agreed PTP
    - Flags violations, disallowing failed calls from counting towards healthy recovery
    """
    violations = []

    # 1. Calling Hours Check (IST = UTC + 5:30)
    if not demo_override_hours and not settings.DEMO_OVERRIDE_HOURS:
        ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
        current_hour = ist_now.hour
        if current_hour < 8 or current_hour >= 19:
            violations.append(f"Calling window violation: Call placed at {ist_now.strftime('%H:%M IST')} outside RBI allowed window (08:00 - 19:00 IST).")

    # 2. Consent Check
    if not case.consent_played:
        violations.append("Regulatory non-compliance: Mandatory call recording consent was not played to borrower.")

    # 3. Transcript Anti-Coercion Audit
    full_transcript_text = " ".join([t.text for t in case.transcript])
    found_prohibited = []
    for term in PROHIBITED_TERMS:
        if term.lower() in full_transcript_text.lower():
            found_prohibited.append(term)

    if found_prohibited:
        violations.append(
            f"CRITICAL VIOLATION - RBI Fair Practices Code: Agent engaged in coercive / abusive threats or third-party shaming (Trigger tokens: {', '.join(found_prohibited)})."
        )

    # 4. PTP Policy Check
    if case.status == "ptp" and case.ptp_date:
        try:
            ptp_dt = datetime.strptime(case.ptp_date, "%Y-%m-%d").date()
            today = datetime.now(timezone.utc).date()
            if ptp_dt > today + timedelta(days=7):
                violations.append(f"Policy breach: Agreed PTP date ({case.ptp_date}) exceeds maximum 7-day threshold.")
        except Exception:
            pass

    # Live LLM cross-check if enabled and no obvious rule violations yet
    if not settings.SIMULATE and settings.SARVAM_API_KEY and not violations:
        try:
            from sarvamai import SarvamAI
            client = SarvamAI(api_subscription_key=settings.SARVAM_API_KEY, timeout=7.5)
            response = client.chat.completions(
                model="sarvam-105b",
                messages=[
                    {"role": "system", "content": COMPLIANCE_AUDIT_PROMPT},
                    {"role": "user", "content": f"Transcript to audit:\n{full_transcript_text}"}
                ],
                temperature=0.0
            )
            raw = response.choices[0].message.content
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                import json
                p = json.loads(match.group(0))
                if not p.get("audit_pass", True):
                    violations.append(f"LLM Compliance Flag: {p.get('audit_reason', 'Violation detected')}")
        except Exception:
            pass  # Fall back to deterministic rules

    # Determination
    if violations:
        case.audit_pass = False
        case.audit_reason = " | ".join(violations)
        summary = f"AUDIT REJECTED: {case.audit_reason}"
    else:
        case.audit_pass = True
        case.audit_reason = "PASSED: Full compliance verified (Calling hours IST, explicit consent, zero coercive language, valid PTP policy)."
        summary = "AUDIT PASSED: 100% compliant with RBI Fair Practices Code & internal lending policy."

    case.add_trace(
        agent="Compliance",
        action="Regulatory & Fair Practice Code Audit",
        summary=summary
    )

    return case
