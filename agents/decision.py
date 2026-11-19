import os
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from app.models import JourneyRecord, WorkflowStep
from app.config import settings

def load_policy_content(policy_path: Optional[str]) -> str:
    if not policy_path:
        return ""
    full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), policy_path)
    if os.path.exists(full_path):
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def run_decision_agent(record: JourneyRecord, step: Optional[WorkflowStep] = None, context: Optional[Dict[str, Any]] = None) -> JourneyRecord:
    """
    Generic Decision Agent (formerly Negotiation):
    - Applies the workflow-specific policy document to the dialogue / situation
    - Operates in SIMULATE mode (deterministic policy rules) or LIVE mode (Sarvam-105B) with auto-fallback
    - Writes decision outcomes (intent, sentiment, offer_made, terms) to record.data
    """
    today = datetime.now(timezone.utc).date()
    max_ptp_date = today + timedelta(days=7)
    policy_text = load_policy_content(context.get("policy_file") if context else "policies/collections_policy.txt")

    # Compile borrower / customer text
    dialogue_texts = [t.text for t in record.transcript if t.speaker in ("borrower", "customer")]
    full_dialogue = " ".join(dialogue_texts).lower()

    workflow_id = record.workflow_id or (context.get("workflow_id") if context else "collections")

    # Handle Loan Sales Workflow
    if workflow_id == "loan_sales":
        return _decision_loan_sales(record, full_dialogue, today)

    # Handle Collections Workflow
    if not settings.SIMULATE and settings.SARVAM_API_KEY:
        try:
            from sarvamai import SarvamAI
            client = SarvamAI(api_subscription_key=settings.SARVAM_API_KEY, timeout=7.5)
            user_msg = f"""
            Policy Document:
            {policy_text}

            Borrower: {record.customer_name}
            Loan ID: {record.data.get('loan_id')}
            Amount Due: ₹{record.amount_due}
            DPD: {record.dpd}
            Dialogue transcript:
            {full_dialogue}
            """
            response = client.chat.completions(
                model="sarvam-105b",
                messages=[
                    {"role": "system", "content": "You are the Decision Agent for Saarthi. Apply the provided policy strictly. Output JSON with: intent ('ptp'|'hardship'|'dispute'|'avoidance'), sentiment, offer_made, ptp_date (YYYY-MM-DD or null), confidence (0.0-1.0), status ('ptp'|'escalated'|'contacted')."},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.1
            )
            raw_content = response.choices[0].message.content
            json_match = re.search(r"\{.*\}", raw_content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                record.intent = parsed.get("intent", "ptp")
                record.sentiment = parsed.get("sentiment", "neutral")
                record.offer_made = parsed.get("offer_made", "Payment commitment requested")
                record.ptp_date = parsed.get("ptp_date")
                record.confidence = float(parsed.get("confidence", 0.9))
                record.status = parsed.get("status", "ptp")
                if record.status == "escalated":
                    record.assigned_human = "Senior Collections Officer"
        except Exception:
            record = _deterministic_negotiate_collections(record, full_dialogue, today, max_ptp_date)
    else:
        record = _deterministic_negotiate_collections(record, full_dialogue, today, max_ptp_date)

    # Post-validation guardrails
    if record.intent in ("dispute", "hardship"):
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

    # Add trace
    record.add_trace(
        agent="Decision",
        action="Policy Verification & Decision Finalized",
        summary=f"Evaluated intent: '{record.intent.upper()}'. Status: {record.status}. Decision: {record.offer_made}. Confidence: {record.confidence*100:.0f}%."
    )

    return record

def _deterministic_negotiate_collections(record: JourneyRecord, text: str, today, max_ptp_date) -> JourneyRecord:
    # 1. Dispute detection
    if any(k in text for k in ["already paid", "cut चुके", "कट गए", "पैसे भर चुका", "गलत", "statement check", "लेजर", "फर्जी"]):
        record.intent = "dispute"
        record.sentiment = "hostile"
        record.status = "escalated"
        record.confidence = 0.98
        record.offer_made = "Dispute flagged: Borrower asserts payment was already debited."
        record.assigned_human = "Dispute Resolution Desk (Ops)"
        return record

    # 2. Hardship / Waiver detection
    if any(k in text for k in ["नोकरी", "job", "अडचण", "हॉस्पिटल", "accident", "सूट", "माफी", "waiver", "restructure", "hospital", "तंगी"]):
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
        record.confidence = 0.88
        record.offer_made = "Call ended abruptly by borrower. Re-queued for retry window."
        return record

    # 4. PTP / Part payment
    record.intent = "ptp"
    record.sentiment = "cooperative"
    record.confidence = 0.94
    record.status = "ptp"
    
    if "5" in text or "५" in text:
        ptp_dt = today + timedelta(days=3)
        record.ptp_date = ptp_dt.strftime("%Y-%m-%d")
        record.offer_made = f"Full payment of ₹{record.amount_due:,.2f} committed for {record.ptp_date}."
    elif any(k in text for k in ["उद्या", "कल", "tomorrow"]):
        ptp_dt = today + timedelta(days=1)
        record.ptp_date = ptp_dt.strftime("%Y-%m-%d")
        record.offer_made = f"Next-day payment commitment for ₹{record.amount_due:,.2f} on {record.ptp_date}."
    elif any(k in text for k in ["30%", "part payment", "हप्ता", "10,000", "15,000"]):
        part_amt = round(record.amount_due * 0.4, 0)
        ptp_dt = today + timedelta(days=5)
        record.ptp_date = ptp_dt.strftime("%Y-%m-%d")
        record.offer_made = f"Part payment of ₹{part_amt:,.2f} immediate + balance due on {record.ptp_date}."
    else:
        ptp_dt = today + timedelta(days=4)
        record.ptp_date = ptp_dt.strftime("%Y-%m-%d")
        record.offer_made = f"Commitment recorded to clear ₹{record.amount_due:,.2f} on {record.ptp_date}."

    return record

def _decision_loan_sales(record: JourneyRecord, text: str, today) -> JourneyRecord:
    # Loan Sales evaluation: Check custom rate / negotiation first
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

# Alias for backward compatibility
run_negotiation_agent = run_decision_agent
