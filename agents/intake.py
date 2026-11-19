import os
from typing import Dict, Any, Optional
from app.models import JourneyRecord, WorkflowStep

def run_intake_agent(record: JourneyRecord, step: Optional[WorkflowStep] = None, context: Optional[Dict[str, Any]] = None) -> JourneyRecord:
    """
    Generic Intake Agent:
    - Reads journey record, normalizes fields
    - Assesses context profile (Collections DPD or Sales Lead quality)
    - Formulates risk_note and tone_hint
    - Establishes best_call_window
    - Writes typed trace record to case file
    """
    workflow_id = record.workflow_id or (context.get("workflow_id") if context else "collections")

    if workflow_id == "loan_sales":
        credit_score = int(record.data.get("credit_score", 750))
        preapproved_amt = float(record.data.get("preapproved_amount", 250000.0))
        record.data["risk_note"] = f"Credit Score: {credit_score} (Tier 1 Prime) | Pre-Approved: ₹{preapproved_amt:,.2f}"
        record.data["tone_hint"] = "Enthusiastic, consultative, highlight instant digital disbursement"
        record.data["best_call_window"] = "11:00 - 16:00 IST"
        summary = f"Qualified pre-approved loan lead for {record.customer_name}. Score: {credit_score}. Limit: ₹{preapproved_amt:,.2f}."
    else:
        # Default: Collections
        if record.dpd <= 3:
            risk_level = "Low Risk (Early Stage)"
            tone = "Friendly reminder, conversational and respectful"
            window = "10:00 - 12:30 IST"
        elif record.dpd <= 15:
            risk_level = "Moderate Risk (T+15 Stage)"
            tone = "Firm but polite, emphasize credit bureau (CIBIL) impact"
            window = "11:00 - 15:00 IST"
        else:
            risk_level = "High Risk (Approaching 30 DPD NPA boundary)"
            tone = "Urgent, structured, direct negotiation on immediate settlement"
            window = "09:30 - 12:00 IST"

        record.data["risk_note"] = f"{risk_level} | DPD: {record.dpd} | Outstanding: ₹{record.amount_due:,.2f}"
        record.data["tone_hint"] = tone
        record.data["best_call_window"] = window
        summary = f"Processed loan {record.data.get('loan_id')} for {record.customer_name}. Language: {record.language}. Assigned profile: {risk_level}."

    # Add trace
    record.add_trace(
        agent="Intake",
        action="Record Profile Loaded & Context Evaluated",
        summary=summary
    )
    
    return record
