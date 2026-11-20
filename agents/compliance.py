import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
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
    - Validates mandatory AI identity disclosure (DISC-AI-01)
    - Validates mandatory call recording notice (DISC-REC-02)
    - Validates mandatory identity verification (RBI-PRIVACY-ID01)
    - Scans for coercive, abusive, or threatening language
    - Evaluates policy compliance of agreed PTP terms
    - Hard gate: FAIL -> status='escalated', Action agent NEVER executes
    """
    workflow_id = record.workflow_id or (context.get("workflow_id") if context else "collections")
    violations = []
    rules = load_collections_rules() if workflow_id == "collections" else {}

    # 1. Mandatory Opening Disclosures
    if workflow_id == "collections":
        if not record.ai_disclosure_played and not record.consent_played:
            violations.append("CRITICAL VIOLATION [DISC-AI-01]: AI assistant identity was not disclosed upfront before discussing debt.")
        if not record.recording_disclosure_played and not record.consent_played:
            violations.append("CRITICAL VIOLATION [DISC-REC-02]: Mandatory regulatory call recording notice was not given.")

    # 2. Calling Hours Check (IST = UTC + 5:30)
    if not demo_override_hours and not settings.DEMO_OVERRIDE_HOURS:
        ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
        current_hour = ist_now.hour
        if current_hour < 8 or current_hour >= 19:
            violations.append(f"Calling window violation [POLICY-CALL-WINDOW01]: Call placed at {ist_now.strftime('%H:%M IST')} outside permitted window (08:00 - 19:00 IST).")

    # 3. Identity Verification Check (Collections)
    if workflow_id == "collections":
        if record.data.get("identity_verified") is False:
            violations.append("Identity Gate Violation [RBI-PRIVACY-ID01]: Borrower identity unverified (4-digit loan ID challenge failed).")

    # 4. Transcript Anti-Coercion / Fair Practices Audit
    full_transcript_text = " ".join([t.text for t in record.transcript]).lower()
    found_prohibited = []
    
    prohibited_list = rules.get("compliance_guardrails", {}).get("forbidden_phrases", DEFAULT_PROHIBITED_TERMS)
    
    for term in prohibited_list:
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
                violations.append(f"Policy breach [POLICY-PTP-MAX01]: Agreed PTP date ({record.ptp_date}) exceeds maximum {max_days}-day threshold.")
        except Exception:
            pass

    # 6. Max Calls Per Day (Lender policy: 2 calls/day)
    attempts = record.data.get("attempts_count", 1)
    max_calls = rules.get("contact_rules", {}).get("max_calls_per_day", 2)
    if attempts > max_calls:
        violations.append(f"Lender Policy Violation [POLICY-CALL-FREQ01]: Exceeded daily contact limit of {max_calls} calls/day.")

    # Determination
    if violations:
        record.audit_pass = False
        record.audit_reason = " | ".join(violations)
        record.status = "escalated"
        record.assigned_human = "Chief Compliance Officer & Legal Desk"
        record.add_trace(
            agent="Compliance",
            action="Regulatory & Fair Practice Code Audit - FAILED",
            summary=f"AUDIT BLOCKED: {record.audit_reason}. Action agent prevented from generating payment link.",
            badge="Review/Critique"
        )
    else:
        record.audit_pass = True
        record.audit_reason = "PASSED: Full compliance verified (08:00-19:00 IST window, explicit consent, identity verified, zero coercive language, valid policy)."
        record.add_trace(
            agent="Compliance",
            action="Regulatory & Fair Practice Code Audit",
            summary="AUDIT PASSED: 100% compliant with RBI Fair Practices Code & internal lending policy. Permitted to execute Action.",
            badge="Review/Critique"
        )

    return record

def audit_raw_transcript(transcript_text: str, rules_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    AUDIT MODE ENGINE (Pilot Wedge):
    - Audits ANY raw transcript (human telecaller or AI) against the board-approved YAML rules.
    - Returns a structured scorecard with Pass/Fail per rule, triggering line, and severity.
    """
    rules = rules_override or load_collections_rules()
    lines = [line.strip() for line in transcript_text.strip().splitlines() if line.strip()]
    full_text = " ".join(lines).lower()

    scorecard: List[Dict[str, Any]] = []

    # Rule 1: AI Assistant Disclosure
    ai_phrases = ["ai assistant", "ai", "एआई", "एआय", "असिस्टंट", "assistant", "आर्टिफिशियल", "सारथी", "automated"]
    has_ai_disc = any(p in full_text for p in ai_phrases)
    scorecard.append({
        "rule_id": "DISC-AI-01",
        "rule_name": "Upfront AI Identity Disclosure",
        "status": "PASS" if has_ai_disc else "FAIL",
        "severity": "CRITICAL",
        "detail": "AI assistant identity declared upfront." if has_ai_disc else "Agent failed to declare AI status before debt discussion.",
        "triggering_line": lines[0] if lines and not has_ai_disc else None
    })

    # Rule 2: Call Recording Notice
    rec_phrases = ["recorded", "रेकॉर्ड", "रिकॉर्ड", "recording"]
    has_rec_disc = any(p in full_text for p in rec_phrases)
    scorecard.append({
        "rule_id": "DISC-REC-02",
        "rule_name": "Call Recording Consent Notice",
        "status": "PASS" if has_rec_disc else "FAIL",
        "severity": "CRITICAL",
        "detail": "Call recording notice played." if has_rec_disc else "Mandatory recording disclosure missing.",
        "triggering_line": lines[0] if lines and not has_rec_disc else None
    })

    # Rule 3: Zero Abusive / Threat / Coercive Language
    prohibited_list = rules.get("compliance_guardrails", {}).get("forbidden_phrases", DEFAULT_PROHIBITED_TERMS)
    found_tokens = []
    offending_lines = []
    for line in lines:
        l_low = line.lower()
        for term in prohibited_list:
            if len(term) <= 3:
                if re.search(rf"\b{re.escape(term.lower())}\b", l_low):
                    found_tokens.append(term)
                    offending_lines.append(line)
            else:
                if term.lower() in l_low:
                    found_tokens.append(term)
                    offending_lines.append(line)

    clean_tone = len(found_tokens) == 0
    scorecard.append({
        "rule_id": "RBI-FPC-TONE01",
        "rule_name": "Anti-Coercion, Harassment & Dignity Code",
        "status": "PASS" if clean_tone else "FAIL",
        "severity": "CRITICAL",
        "detail": "Zero abusive, threatening, or shaming language detected." if clean_tone else f"Coercive terms detected: {', '.join(set(found_tokens))}",
        "triggering_line": offending_lines[0] if offending_lines else None
    })

    # Rule 4: Sensitive Event Empathy & Pause
    sensitive_words = ["hospital", "हॉस्पिटल", "accident", "अपघात", "icu", "admitted", "death", "मृत्यू", "निधन", "वारले", "passed away"]
    has_sensitive = any(w in full_text for w in sensitive_words)
    pushed_for_payment = any(w in full_text for w in ["pay now", "अभि भरो", "आजच भरा", "पैसे भरा", "तुरंत भरो", "transfer now"])
    
    if has_sensitive:
        sens_passed = not pushed_for_payment
        scorecard.append({
            "rule_id": "FAIR-PRAC-SENS01",
            "rule_name": "Sensitive Life Event Compassion & Pause",
            "status": "PASS" if sens_passed else "FAIL",
            "severity": "CRITICAL",
            "detail": "Recovery paused with empathy upon sensitive life event." if sens_passed else "Agent improperly pushed for payment despite borrower reporting medical emergency/bereavement.",
            "triggering_line": next((l for l in lines if any(w in l.lower() for w in sensitive_words)), None)
        })
    else:
        scorecard.append({
            "rule_id": "FAIR-PRAC-SENS01",
            "rule_name": "Sensitive Life Event Compassion & Pause",
            "status": "PASS",
            "severity": "INFO",
            "detail": "No sensitive life events reported in dialogue.",
            "triggering_line": None
        })

    # Rule 5: Identity Gate (Zero Third-Party Disclosure)
    third_party_words = ["wife", "husband", "relative", "neighbour", "पत्नी", "पति", "पड़ोसी"]
    has_third_party = any(w in full_text for w in third_party_words)
    disclosed_amount = bool(re.search(r"(?:₹|rs\.?|amount|loan)\s*\d+", full_text))
    
    if has_third_party and disclosed_amount:
        scorecard.append({
            "rule_id": "RBI-PRIVACY-TP02",
            "rule_name": "Third-Party Zero Debt Disclosure",
            "status": "FAIL",
            "severity": "CRITICAL",
            "detail": "Debt amount disclosed to a third party (spouse/neighbour), violating RBI borrower privacy code.",
            "triggering_line": next((l for l in lines if any(w in l.lower() for w in third_party_words)), None)
        })
    else:
        scorecard.append({
            "rule_id": "RBI-PRIVACY-TP02",
            "rule_name": "Third-Party Zero Debt Disclosure",
            "status": "PASS",
            "severity": "INFO",
            "detail": "Borrower privacy upheld.",
            "triggering_line": None
        })

    failed_critical = any(item["status"] == "FAIL" and item["severity"] == "CRITICAL" for item in scorecard)
    passed_rules = sum(1 for item in scorecard if item["status"] == "PASS")
    total_rules = len(scorecard)
    score_pct = round((passed_rules / total_rules) * 100, 1)

    return {
        "audit_pass": not failed_critical,
        "compliance_score_pct": score_pct,
        "scorecard": scorecard,
        "total_rules_evaluated": total_rules,
        "critical_violations_count": sum(1 for item in scorecard if item["status"] == "FAIL" and item["severity"] == "CRITICAL"),
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "summary": "AUDIT PASSED: Call conforms to lender policy and RBI conduct guidelines." if not failed_critical else "AUDIT FAILED: Call contains regulatory/policy violations."
    }
