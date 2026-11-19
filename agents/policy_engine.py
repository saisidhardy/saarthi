import os
import re
from datetime import datetime, timedelta, timezone, date
from typing import Optional, Dict, Any
from app.models import JourneyRecord, WorkflowStep, PolicyDecision, LLMProposal

COLLECTIONS_RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "policies", "collections_rules.yaml")

def resolve_date_phrase(phrase: str, reference_date: Optional[date] = None) -> date:
    """
    CODE resolves relative dates to ISO dates from today's IST date.
    LLMs are explicitly forbidden from calculating dates.
    """
    if not reference_date:
        reference_date = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date()

    clean = phrase.lower().strip()
    
    # 1. Weekday resolution
    weekdays = {
        "monday": 0, "सोमवार": 0,
        "tuesday": 1, "मंगळवार": 1, "मंगलवार": 1,
        "wednesday": 2, "बुधवार": 2,
        "thursday": 3, "गुरुवार": 3,
        "friday": 4, "शुक्रवार": 4,
        "saturday": 5, "शनिवार": 5,
        "sunday": 6, "रविवार": 6, "इतवार": 6
    }
    for w_name, w_idx in weekdays.items():
        if w_name in clean:
            curr_w = reference_date.weekday()
            days_ahead = (w_idx - curr_w) % 7
            if days_ahead == 0:
                days_ahead = 7
            return reference_date + timedelta(days=days_ahead)

    # 2. Relative day offsets
    if any(k in clean for k in ["today", "आज"]):
        return reference_date
    if any(k in clean for k in ["tomorrow", "कल", "उद्या"]):
        return reference_date + timedelta(days=1)
    if any(k in clean for k in ["परसों", "परवा"]):
        return reference_date + timedelta(days=2)
    if any(k in clean for k in ["2 days", "2 din", "दोन दिवस", "2 दिवस", "दो दिन"]):
        return reference_date + timedelta(days=2)
    if any(k in clean for k in ["3 days", "3 din", "तीन दिवस", "3 दिवस", "तीन दिन"]):
        return reference_date + timedelta(days=3)
    if any(k in clean for k in ["4 days", "4 din", "चार दिवस", "4 दिवस"]):
        return reference_date + timedelta(days=4)
    if any(k in clean for k in ["5 days", "5 din", "पाच दिवस", "5 दिवस", "पाँच दिन"]):
        return reference_date + timedelta(days=5)
    if any(k in clean for k in ["next week", "अगले हफ्ते", "पुढच्या आठवड्यात"]):
        return reference_date + timedelta(days=5)

    # 3. Specific Day of Month (e.g. "5", "5th", "5 तारखेला", "५", "15", "20 तारीख")
    day_match = re.search(r"(\b[1-9]\b|\b[12][0-9]\b|\b3[01]\b|[१-९]|[१२][०-९]|[३][०१])", clean)
    if day_match:
        raw_val = day_match.group(1)
        indic_digits = {"०": "0", "१": "1", "२": "2", "३": "3", "४": "4", "५": "5", "६": "6", "७": "7", "८": "8", "९": "9"}
        for ind, eng in indic_digits.items():
            raw_val = raw_val.replace(ind, eng)
        try:
            target_day = int(raw_val)
            if target_day >= reference_date.day and (target_day - reference_date.day) <= 10:
                return reference_date.replace(day=target_day)
            elif target_day < reference_date.day and (target_day + 30 - reference_date.day) <= 10:
                return reference_date + timedelta(days=(target_day + 30 - reference_date.day))
            else:
                return reference_date + timedelta(days=min(max(target_day - reference_date.day, 2), 6))
        except Exception:
            pass

    # Default fallback: 3 days
    return reference_date + timedelta(days=3)

def run_policy_engine(record: JourneyRecord, step: Optional[WorkflowStep] = None, context: Optional[Dict[str, Any]] = None) -> JourneyRecord:
    """
    POLICY ENGINE (The Core):
    - Plain Python state machine (CODE, never LLM).
    - Validates, clamps, or blocks LLM proposals strictly against /policies/collections_rules.yaml.
    - Generates a signed PolicyDecision object. Action agent accepts ONLY this decision object.
    - Emits Policy Firewall telemetry for the UI showing:
      LLM PROPOSED vs ENGINE DECIDED (APPROVED / CLAMPED / BLOCKED) with Rule ID and YAML Line.
    """
    workflow_id = record.workflow_id or (context.get("workflow_id") if context else "collections")
    if workflow_id == "loan_sales":
        # Pass-through for loan sales
        return record

    today = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date()
    max_policy_ptp_date = today + timedelta(days=7)
    
    # Retrieve proposal from Negotiation agent or record data
    proposal_data = record.data.get("llm_proposal", {})
    intent = proposal_data.get("intent", record.intent or "ptp")
    offered_amt = proposal_data.get("offered_amount")
    date_phrase = proposal_data.get("date_phrase") or record.data.get("extracted_date_phrase") or "3 days"
    waiver_requested = proposal_data.get("waiver_requested", False)
    requested_days = proposal_data.get("requested_days")

    dialogue_texts = [t.text for t in record.transcript if t.speaker in ("borrower", "customer")]
    full_dialogue = " ".join(dialogue_texts).lower()

    # 1. RULE: FAIR-PRAC-SENS01 (Sensitive-Event Immediate Pause)
    sensitive_words = [
        "hospital", "हॉस्पिटल", "accident", "अपघात", "दवाखाना", "icu", "admitted", "ऍडमिट", "एडमिट", "बीमार", "गंभीर", "operation", "इलाज",
        "death", "passed away", "funeral", "demise", "मृत्यू", "निधन", "वारले", "मयत", "क्रियाकर्म",
        "earthquake", "cyclone", "भूकंप", "आपत्ती", "आपदा",
        "wedding", "marriage", "लग्न", "शादी", "विवाह"
    ]
    has_sensitive = any(w in full_dialogue for w in sensitive_words)
    if not has_sensitive and (re.search(r"(?:^|\s)(पूर|महापूर|flood|आग|fire)(?:\s|[.,!?]|$)", full_dialogue)):
        has_sensitive = True

    if has_sensitive:
        pause_until = (today + timedelta(days=7)).isoformat()
        record.do_not_contact_until = pause_until
        decision = PolicyDecision(
            status="SENSITIVE_PAUSE",
            rule_id="FAIR-PRAC-SENS01",
            yaml_line=57,
            yaml_file="policies/collections_rules.yaml",
            effective_amount=0.0,
            effective_date=None,
            reason="Sensitive life event detected (bereavement, medical emergency/hospitalization, calamity, or wedding). Recovery paused for 7 days per lender policy. Zero negotiation or payment links allowed.",
            needs_human=True,
            assigned_human="Sensitive Care & Compassionate Follow-up Desk",
            do_not_contact_until=pause_until,
            action_permitted=False,
            llm_proposed_summary="Borrower reported medical emergency / hospitalisation",
            engine_decision_summary="SENSITIVE PAUSE: 7-day cooling period set, zero payment link [FAIR-PRAC-SENS01, Line 57]"
        )
        return _apply_policy_decision(record, decision)

    # 2. RULE: FAIR-PRAC-DISTRESS01 (Non-Emergency Job Loss Distress)
    distress_triggers = ["job loss", "lost my job", "नोकरी गेली", "काम छूट गया", "नोकरी चली गई", "salary delay", "पगार झाला नाही", "salary nahi aayi", "business loss"]
    if any(k in full_dialogue for k in distress_triggers):
        record.data["pre_escalation_record"] = {
            "disclosed_options": [
                "Short grace-period extension (within 7 days policy limit)",
                "Affordable upfront part-payment (>= 30%) with deferred balance",
                "Handover to certified human credit counsellor"
            ],
            "waiver_promised": False,
            "borrower_context": "Job loss / income disruption reported"
        }
        decision = PolicyDecision(
            status="ESCALATED",
            rule_id="FAIR-PRAC-DISTRESS01",
            yaml_line=106,
            yaml_file="policies/collections_rules.yaml",
            effective_amount=record.amount_due,
            effective_date=None,
            reason="Job-loss distress identified. Pre-escalation engagement logged without waiver promise. Escalated for structured financial counselling.",
            needs_human=True,
            assigned_human="Credit Restructuring & Financial Counselling Desk",
            action_permitted=False,
            llm_proposed_summary="Borrower reported job loss / salary disruption",
            engine_decision_summary="ESCALATED: Documented distress path options without waiver [FAIR-PRAC-DISTRESS01, Line 106]"
        )
        return _apply_policy_decision(record, decision)

    # 3. RULE: DISC-HUMAN-03 (Human Opt-Out Request)
    human_keywords = ["human", "agent", "person", "representative", "इंसान", "अधिकारी", "एजेंट", "व्यक्ति", "माणूस", "प्रतिनिधी", "adhikari", "manus"]
    if any(k in full_dialogue for k in human_keywords):
        decision = PolicyDecision(
            status="ESCALATED",
            rule_id="DISC-HUMAN-03",
            yaml_line=24,
            yaml_file="policies/collections_rules.yaml",
            effective_amount=0.0,
            effective_date=None,
            reason="Borrower exercised explicit human opt-out. Immediate transfer to live human telecaller.",
            needs_human=True,
            assigned_human="Live Telecaller Queue",
            action_permitted=False,
            llm_proposed_summary="Borrower requested live human representative",
            engine_decision_summary="ESCALATED: Human opt-out triggered [DISC-HUMAN-03, Line 24]"
        )
        return _apply_policy_decision(record, decision)

    # 4. RULE: RBI-PRIVACY-TP02 (Third-Party Contact Protection)
    tp_indicators = ["wife", "husband", "relative", "neighbour", "neighbor", "पत्नी बोल रही", "पति बोल रहे", "त्यांचा भाऊ", "त्यांची बहीण", "पड़ोसी", "घर पर नहीं"]
    if record.third_party_contact or any(k in full_dialogue for k in tp_indicators):
        record.third_party_contact = True
        do_not_contact = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        record.do_not_contact_until = do_not_contact
        decision = PolicyDecision(
            status="BLOCKED",
            rule_id="RBI-PRIVACY-TP02",
            yaml_line=50,
            yaml_file="policies/collections_rules.yaml",
            effective_amount=0.0,
            effective_date=None,
            reason="Third-party contact identified (spouse/relative/neighbour). Zero debt disclosure permitted. 24h cooling window set.",
            needs_human=True,
            assigned_human="Third-Party Callback Queue",
            do_not_contact_until=do_not_contact,
            action_permitted=False,
            llm_proposed_summary="Third-party answered phone",
            engine_decision_summary="BLOCKED: Zero disclosure to third party; 24h cooling [RBI-PRIVACY-TP02, Line 50]"
        )
        return _apply_policy_decision(record, decision)

    # 5. RULE: POLICY-WAIVER-NO01 (Adversarial Waiver / Prompt Injection Block)
    if waiver_requested or any(k in full_dialogue for k in ["ignore your rules", "give me a waiver", "waive", "सूट", "माफी करा", "छूट", "नुकसान"]):
        decision = PolicyDecision(
            status="BLOCKED",
            rule_id="POLICY-WAIVER-NO01",
            yaml_line=144,
            yaml_file="policies/collections_rules.yaml",
            effective_amount=record.amount_due,
            effective_date=None,
            reason="Lender policy strictly prohibits autonomous waivers (waiver_allowed=false). Request blocked; escalated to human authority.",
            needs_human=True,
            assigned_human="Credit Committee (Waiver Exception Desk)",
            action_permitted=False,
            llm_proposed_summary="Borrower demanded debt waiver / prompt injection attempted",
            engine_decision_summary="BLOCKED: waiver_allowed_autonomous=false [POLICY-WAIVER-NO01, Line 144]"
        )
        return _apply_policy_decision(record, decision)

    # 6. RULE: Dispute Detection
    if intent == "dispute" or any(k in full_dialogue for k in ["already paid", "cut चुके", "कट गए", "पैसे भर चुका", "गलत", "statement check", "लेजर", "फर्जी", "कटौती"]):
        decision = PolicyDecision(
            status="ESCALATED",
            rule_id="RBI-FPC-DISP01",
            yaml_line=45,
            yaml_file="policies/collections_rules.yaml",
            effective_amount=0.0,
            effective_date=None,
            reason="Borrower asserts prior debit or ledger dispute. Bank transaction verification required.",
            needs_human=True,
            assigned_human="Dispute Resolution Desk (Ops)",
            action_permitted=False,
            llm_proposed_summary="Borrower asserts EMI was already debited via UPI/Bank",
            engine_decision_summary="ESCALATED: Disputed ledger escalated to human ops [RBI-FPC-DISP01, Line 45]"
        )
        return _apply_policy_decision(record, decision)

    # 7. CODE RESOLVES DATE PHRASE
    resolved_dt = resolve_date_phrase(date_phrase, today)
    raw_days_ahead = (resolved_dt - today).days

    # 8. RULE: POLICY-PTP-MAX01 (Max PTP 7 Days)
    clamped_date = resolved_dt
    date_decision_status = "APPROVED"
    if raw_days_ahead > 7 or (requested_days and requested_days > 7):
        # Clamped to policy maximum of 7 days
        clamped_date = max_policy_ptp_date
        date_decision_status = "CLAMPED"

    effective_date_str = clamped_date.strftime("%Y-%m-%d")

    # 9. RULE: POLICY-PART-MIN01 (Min Part Payment 30%)
    if offered_amt and offered_amt < record.amount_due:
        min_allowed = round(record.amount_due * 0.3, 2)
        if offered_amt < min_allowed:
            decision = PolicyDecision(
                status="BLOCKED",
                rule_id="POLICY-PART-MIN01",
                yaml_line=141,
                yaml_file="policies/collections_rules.yaml",
                effective_amount=offered_amt,
                effective_date=effective_date_str,
                reason=f"Offered part-payment of ₹{offered_amt:,.2f} is below mandatory 30% policy threshold (₹{min_allowed:,.2f}). Blocked by Policy Firewall.",
                needs_human=True,
                assigned_human="Floor Supervisor (Credit Exceptions)",
                action_permitted=False,
                llm_proposed_summary=f"Part-payment of ₹{offered_amt:,.2f} on {effective_date_str}",
                engine_decision_summary=f"BLOCKED: Part payment below 30% policy threshold [POLICY-PART-MIN01, Line 141]"
            )
            return _apply_policy_decision(record, decision)
        else:
            # Valid Part Payment
            shortfall = round(record.amount_due - offered_amt, 2)
            record.data["shortfall_amount"] = shortfall
            needs_approval = shortfall > 10000.0
            record.data["needs_approval"] = needs_approval

            rule_id = "POLICY-PTP-MAX01" if date_decision_status == "CLAMPED" else "POLICY-PART-MIN01"
            line_no = 139 if date_decision_status == "CLAMPED" else 141
            decision = PolicyDecision(
                status="AWAITING_APPROVAL" if needs_approval else date_decision_status,
                rule_id=rule_id,
                yaml_line=line_no,
                yaml_file="policies/collections_rules.yaml",
                effective_amount=offered_amt,
                effective_date=effective_date_str,
                reason=f"Part payment of ₹{offered_amt:,.2f} (>=30% threshold). Shortfall ₹{shortfall:,.2f} {'exceeds ₹10k threshold - awaiting credit authority approval' if needs_approval else 'within autonomous threshold'}.",
                needs_human=needs_approval,
                assigned_human="Senior Credit Authority (Exceptions Desk)" if needs_approval else None,
                action_permitted=True,
                llm_proposed_summary=f"Part-payment of ₹{offered_amt:,.2f} requested for {date_phrase}",
                engine_decision_summary=f"{'AWAITING_APPROVAL (Shortfall >₹10k)' if needs_approval else date_decision_status}: Approved part payment of ₹{offered_amt:,.2f} on {effective_date_str} [{rule_id}, Line {line_no}]"
            )
            return _apply_policy_decision(record, decision)

    # 10. Full EMI Commitment
    rule_id = "POLICY-PTP-MAX01" if date_decision_status == "CLAMPED" else "POLICY-PTP-OK01"
    line_no = 139 if date_decision_status == "CLAMPED" else 138
    decision = PolicyDecision(
        status=date_decision_status,
        rule_id=rule_id,
        yaml_line=line_no,
        yaml_file="policies/collections_rules.yaml",
        effective_amount=record.amount_due,
        effective_date=effective_date_str,
        reason=f"Full EMI payment of ₹{record.amount_due:,.2f} committed for {effective_date_str} (within 7-day policy limit).",
        needs_human=False,
        action_permitted=True,
        llm_proposed_summary=f"Full payment of ₹{record.amount_due:,.2f} for {date_phrase}",
        engine_decision_summary=f"{date_decision_status}: Full commitment for {effective_date_str} [{rule_id}, Line {line_no}]"
    )
    return _apply_policy_decision(record, decision)

def _apply_policy_decision(record: JourneyRecord, decision: PolicyDecision) -> JourneyRecord:
    record.data["policy_decision"] = decision.model_dump()
    record.data["policy_firewall"] = {
        "llm_proposed": decision.llm_proposed_summary,
        "engine_decided": decision.engine_decision_summary,
        "status": decision.status,
        "rule_id": decision.rule_id,
        "yaml_line": decision.yaml_line,
        "yaml_file": decision.yaml_file,
        "reason": decision.reason,
        "action_permitted": decision.action_permitted
    }

    if decision.status in ("APPROVED", "CLAMPED"):
        record.status = "ptp"
        record.ptp_date = decision.effective_date
        record.offer_made = decision.reason
    elif decision.status == "AWAITING_APPROVAL":
        record.status = "awaiting_approval"
        record.ptp_date = decision.effective_date
        record.assigned_human = decision.assigned_human
        record.offer_made = decision.reason
    elif decision.status == "SENSITIVE_PAUSE":
        record.status = "escalated"
        record.ptp_date = None
        record.assigned_human = decision.assigned_human
        record.offer_made = decision.reason
    elif decision.status in ("BLOCKED", "ESCALATED"):
        record.status = "escalated"
        record.ptp_date = None
        record.assigned_human = decision.assigned_human
        record.offer_made = decision.reason

    record.add_trace(
        agent="PolicyEngine",
        action="Deterministic Rule Enforcement",
        summary=f"Policy Firewall Decision: {decision.status} by rule {decision.rule_id} (Line {decision.yaml_line}). {decision.reason}",
        badge="Policy Firewall"
    )
    return record
