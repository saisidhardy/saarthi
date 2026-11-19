import os
import csv
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.models import CaseFile, TraceItem
from app.config import settings

def run_intake_agent(case: CaseFile) -> CaseFile:
    """
    Intake Agent:
    - Reads case data, normalizes language & DPD
    - Assesses risk profile based on DPD & amount
    - Formulates risk_note and tone_hint
    - Establishes best_call_window
    - Writes typed trace record to case file
    """
    # Risk and Tone assessment
    if case.dpd <= 3:
        risk_level = "Low Risk (Early Stage)"
        tone = "Friendly reminder, conversational and respectful"
        window = "10:00 - 12:30 IST"
    elif case.dpd <= 15:
        risk_level = "Moderate Risk (T+15 Stage)"
        tone = "Firm but polite, emphasize credit bureau (CIBIL) impact"
        window = "11:00 - 15:00 IST"
    else:
        risk_level = "High Risk (Approaching 30 DPD NPA boundary)"
        tone = "Urgent, structured, direct negotiation on immediate settlement"
        window = "09:30 - 12:00 IST"

    case.risk_note = f"{risk_level} | DPD: {case.dpd} | Outstanding: ₹{case.amount_due:,.2f}"
    case.tone_hint = tone
    case.best_call_window = window

    # Add trace
    case.add_trace(
        agent="Intake",
        action="Account Profile Loaded & Risk Assessed",
        summary=f"Processed loan {case.loan_id} for {case.borrower_name}. Language: {case.language}. Assigned profile: {risk_level}."
    )
    
    return case
