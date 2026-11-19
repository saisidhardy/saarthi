import os
import json
import re
from datetime import datetime, timedelta, timezone, date
from typing import Optional, Dict, Any
from app.models import JourneyRecord, WorkflowStep
from app.config import settings
from services.sarvam import sarvam_service

def load_policy_content(policy_path: Optional[str]) -> str:
    if not policy_path:
        return ""
    full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), policy_path)
    if os.path.exists(full_path):
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def resolve_date_phrase(phrase: str, reference_date: Optional[date] = None) -> date:
    """
    CODE resolves relative dates to ISO dates from today's date.
    LLMs are explicitly forbidden from calculating dates.
    """
    if not reference_date:
        # Current IST date (UTC + 5:30)
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
                # Next month's target day within 10 days
                return reference_date + timedelta(days=(target_day + 30 - reference_date.day))
            else:
                return reference_date + timedelta(days=min(max(target_day - reference_date.day, 2), 6))
        except Exception:
            pass

    # Default fallback: 3 days
    return reference_date + timedelta(days=3)

def extract_amount_from_speech(text: str, total_due: float, loan_id: Optional[str] = None) -> Optional[float]:
    """
    Extracts numerical payment amounts from spoken Hinglish/Marathi text.
    Handles 'half', '10k', '₹10,000', '2500', full payment phrases ('पूर्ण', 'सर्व', 'पूरा', 'full').
    Explicitly filters out loan_id digits (e.g. 1001, 1002) so identity verification numbers aren't confused with money.
    """
    clean = text.lower()
    
    # 1. Full payment indicators in Marathi, Hindi, English
    if any(k in clean for k in ["पूर्ण", "पूरा", "पूरे", "all", "full", "complete", "संपूर्ण", "सर्व", "सगळे", "नक्की सर्व", "full payment"]):
        return total_due

    # 2. Check for half / 50%
    if any(k in clean for k in ["half", "आधा", "निम्मे", "50%"]):
        return round(total_due * 0.5, 2)
    
    # 3. 10k style
    k_match = re.search(r"(\d+(?:\.\d+)?)\s*k\b", clean)
    if k_match:
        return float(k_match.group(1)) * 1000.0

    # 4. Extract loan digits to ignore (e.g. 1001, 1002)
    loan_digits = ""
    if loan_id:
        loan_digits = re.sub(r"\D", "", str(loan_id))[-4:]

    # 5. Numerical search
    matches = re.finditer(r"(?:rs\.?|inr|₹)?\s*(\d{1,3}(?:,\d{3})+|\d{4,6}|\d{3})", clean)
    found_amounts = []
    for m in matches:
        raw = m.group(1).replace(",", "")
        try:
            val = float(raw)
            # Skip loan verification digits
            if loan_digits and raw == loan_digits:
                continue
            if 100 <= val <= total_due:
                found_amounts.append(val)
        except ValueError:
            continue

    if found_amounts:
        # If there are part payment numbers (e.g. 10,000 out of 25,000), return the part payment
        part_payments = [v for v in found_amounts if v < total_due]
        if part_payments:
            return part_payments[0]
        return found_amounts[0]

    return None

def run_decision_agent(record: JourneyRecord, step: Optional[WorkflowStep] = None, context: Optional[Dict[str, Any]] = None) -> JourneyRecord:
    """
    Generic Decision Agent (Negotiation):
    - Uses Sarvam-105B or deterministic policy to extract borrower intent, amount, and date phrase.
    - Python CODE computes and resolves relative dates to ISO dates.
    - Validates against policy (PTP <= 7 days, Part payment >= 30%).
    """
    # Current IST date
    today = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date()
    max_ptp_date = today + timedelta(days=7)

    dialogue_texts = [t.text for t in record.transcript if t.speaker in ("borrower", "customer")]
    full_dialogue = " ".join(dialogue_texts).lower()

    workflow_id = record.workflow_id or (context.get("workflow_id") if context else "collections")

    if workflow_id == "loan_sales":
        return _decision_loan_sales(record, full_dialogue, today)

    # Collections Workflow
    if not settings.SIMULATE and settings.SARVAM_API_KEY and settings.SARVAM_API_KEY != "mock_sarvam_key":
        try:
            user_msg = f"""
            Borrower: {record.customer_name}
            Loan ID: {record.data.get('loan_id')}
            Amount Due: ₹{record.amount_due}
            DPD: {record.dpd}
            Dialogue transcript:
            {full_dialogue}

            Extract:
            1. intent: 'ptp' | 'hardship' | 'dispute' | 'avoidance'
            2. sentiment: 'positive' | 'neutral' | 'anxious' | 'hostile'
            3. extracted_amount: integer or null (e.g. if borrower says half or 10000)
            4. extracted_date_phrase: exact relative date text (e.g. 'Friday', '5th', 'tomorrow', '2 days')
            Output JSON only. Do not compute dates.
            """
            content = sarvam_service.chat_completion(
                messages=[
                    {"role": "system", "content": "You are the Decision Agent for Saarthi. Extract intent, sentiment, extracted_amount, and extracted_date_phrase. Do NOT compute ISO dates."},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.1
            )
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                record.intent = parsed.get("intent", "ptp")
                record.sentiment = parsed.get("sentiment", "neutral")
                
                # CODE resolves date phrase
                date_phrase = parsed.get("extracted_date_phrase") or "3 days"
                resolved_dt = resolve_date_phrase(date_phrase, today)
                if resolved_dt > max_ptp_date:
                    resolved_dt = max_ptp_date
                record.ptp_date = resolved_dt.strftime("%Y-%m-%d")

                # CODE checks amount
                ext_amt = parsed.get("extracted_amount")
                if ext_amt and float(ext_amt) >= (record.amount_due * 0.3):
                    record.offer_made = f"Part-payment of ₹{float(ext_amt):,.2f} accepted upfront. Balance due on {record.ptp_date}."
                    record.status = "ptp"
                else:
                    record.offer_made = f"Full payment commitment for ₹{record.amount_due:,.2f} on {record.ptp_date}."
                    record.status = "ptp" if record.intent == "ptp" else "escalated"
                record.confidence = 0.95
        except Exception:
            record = _deterministic_negotiate_collections(record, full_dialogue, today, max_ptp_date)
    else:
        record = _deterministic_negotiate_collections(record, full_dialogue, today, max_ptp_date)

    # Post-validation guardrails
    if record.status == "awaiting_approval":
        pass
    elif record.intent in ("dispute", "hardship"):
        record.status = "escalated"
        record.ptp_date = None
        if record.intent == "dispute":
            record.assigned_human = "Dispute Resolution Desk (Ops)"
            record.offer_made = "Disputed ledger: Escalated to human with bank transaction audit log."
        else:
            record.assigned_human = "Credit Committee (Hardship & Restructure)"
            record.offer_made = "Restructure/Waiver requested: Automated waiver rejected; passed to human authority."
    elif record.intent == "avoidance":
        record.status = "contacted"
        record.offer_made = "Follow-up reminder call scheduled within 24 hours."
    else:
        record.status = "ptp"
        if not record.ptp_date:
            record.ptp_date = (today + timedelta(days=3)).strftime("%Y-%m-%d")

    record.add_trace(
        agent="Decision",
        action="Policy Verification & Decision Finalized",
        summary=f"Evaluated intent: '{record.intent.upper()}'. Status: {record.status}. Decision: {record.offer_made}. Confidence: {record.confidence*100:.0f}%."
    )

    return record

def _deterministic_negotiate_collections(record: JourneyRecord, text: str, today: date, max_ptp_date: date) -> JourneyRecord:
    # 1. Dispute detection
    if any(k in text for k in ["already paid", "cut चुके", "कट गए", "पैसे भर चुका", "गलत", "statement check", "लेजर", "फर्जी", "कटौती"]):
        record.intent = "dispute"
        record.sentiment = "hostile"
        record.status = "escalated"
        record.confidence = 0.98
        record.offer_made = "Dispute flagged: Borrower asserts payment was already debited."
        record.assigned_human = "Dispute Resolution Desk (Ops)"
        return record

    # 2. Hardship / Waiver / Restructure detection
    if any(k in text for k in ["नोकरी", "job", "अडचण", "हॉस्पिटल", "accident", "सूट", "माफी", "waiver", "restructure", "hospital", "तंगी", "lost my job", "waive"]):
        shortfall = record.amount_due - min(record.amount_due * 0.3, 10000.0)
        if shortfall > 10000.0 and record.data.get("approval_decision") is None:
            record.intent = "hardship"
            record.sentiment = "anxious"
            record.status = "awaiting_approval"
            record.data["needs_approval"] = True
            record.data["shortfall_amount"] = shortfall
            record.confidence = 0.96
            record.offer_made = f"Restructure requested: Shortfall of ₹{shortfall:,.2f} exceeds ₹10,000 threshold. Paused for Human Approval."
            return record
        elif record.data.get("approval_decision") == "approved":
            record.intent = "ptp"
            record.status = "ptp"
            record.offer_made = f"Restructure approved by Credit Committee: Balance of ₹{shortfall:,.2f} restructured."
            record.confidence = 0.98
            record.ptp_date = (today + timedelta(days=5)).strftime("%Y-%m-%d")
            return record
        else:
            record.intent = "hardship"
            record.sentiment = "anxious"
            record.status = "escalated"
            record.confidence = 0.95
            record.offer_made = "Hardship detected: Borrower seeks EMI restructuring/waiver. Flagged for human review."
            record.assigned_human = "Credit Committee (Hardship Desk)"
            return record

    # 3. Avoidance detection
    if any(k in text for k in ["मीटिंग", "meeting", "busy", "बाद में", "फोन काटो", "काट दिया", "disconnect"]):
        record.intent = "avoidance"
        record.sentiment = "neutral"
        record.status = "contacted"
        record.confidence = 0.90
        record.offer_made = "Follow-up reminder call scheduled within 24 hours."
        return record

    # 4. PTP and Part-Payment Parsing in CODE
    record.intent = "ptp"
    record.sentiment = "positive"
    record.confidence = 0.95

    # CODE resolves date phrase
    resolved_dt = resolve_date_phrase(text, today)
    if resolved_dt > max_ptp_date:
        resolved_dt = max_ptp_date
    record.ptp_date = resolved_dt.strftime("%Y-%m-%d")

    # CODE extracts amount
    offered_amt = extract_amount_from_speech(text, record.amount_due, loan_id=record.data.get("loan_id"))
    if offered_amt and offered_amt < record.amount_due:
        min_allowed = round(record.amount_due * 0.3, 2)
        if offered_amt >= min_allowed:
            record.data["part_payment_offered"] = offered_amt
            remaining = record.amount_due - offered_amt
            record.offer_made = f"Part-payment of ₹{offered_amt:,.2f} accepted upfront (>=30%). Balance ₹{remaining:,.2f} due on {record.ptp_date}."
            record.status = "ptp"
        else:
            record.intent = "hardship"
            record.status = "escalated"
            record.assigned_human = "Floor Supervisor"
            record.offer_made = f"Offered part-payment of ₹{offered_amt:,.2f} is below 30% policy threshold (₹{min_allowed:,.2f}). Escalated."
    else:
        record.offer_made = f"Full payment of ₹{record.amount_due:,.2f} committed for {record.ptp_date}."
        record.status = "ptp"

    return record

def _decision_loan_sales(record: JourneyRecord, text: str, today: date) -> JourneyRecord:
    if any(k in text for k in ["negotiat", "rate is high", "8.75%", "8.5%", "concession", "कम ब्याज", "कमी करा"]):
        record.intent = "hardship"
        record.status = "escalated"
        record.offer_made = "Custom interest rate concession requested. Escalated to Senior Relationship Manager."
        record.assigned_human = "Senior Relationship Manager (Elite Sales)"
        record.confidence = 0.95
    elif any(k in text for k in ["not interested", "मत करो", "नको", "stop calling"]):
        record.intent = "avoidance"
        record.status = "contacted"
        record.offer_made = "Customer declined loan offer. Placed on DNC list."
        record.confidence = 0.99
    elif any(k in text for k in ["yes", "interested", "चाहिए", "होय", "कितना मिलेगा", "ब्याज"]):
        record.intent = "ptp"
        record.status = "qualified"
        pre_amt = record.data.get("preapproved_amount", 200000)
        record.offer_made = f"Pre-approved loan of ₹{pre_amt:,.2f} accepted by customer. Documents requested."
        record.confidence = 0.95
    else:
        record.intent = "ptp"
        record.status = "qualified"
        record.offer_made = "Lead qualified for personal loan disbursement."
        record.confidence = 0.90

    record.add_trace(
        agent="Decision",
        action="Sales Offer Evaluation",
        summary=f"Sales decision: Status={record.status}. Intent={record.intent}. Offer={record.offer_made}."
    )
    return record

run_negotiation_agent = run_decision_agent
