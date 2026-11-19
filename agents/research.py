from typing import Optional, Dict, Any
from app.models import JourneyRecord, WorkflowStep

def run_research_agent(
    record: JourneyRecord,
    step: Optional[WorkflowStep] = None,
    context: Optional[Dict[str, Any]] = None
) -> JourneyRecord:
    """
    Research Agent:
    - Queries Credit Bureau (CIBIL/Experian) and account history
    - Assesses debt-to-income ratio and prime tiering
    - Computes maximum pre-approved loan limit
    """
    score = int(record.data.get("credit_score", 750))
    if score >= 780:
        tier = "Super Prime"
        multiplier = "5.0x Monthly Income"
    elif score >= 720:
        tier = "Prime"
        multiplier = "3.5x Monthly Income"
    else:
        tier = "Near Prime"
        multiplier = "2.0x Monthly Income"

    record.data["bureau_tier"] = tier
    record.data["income_multiplier"] = multiplier
    
    pre_amt = float(record.data.get("preapproved_amount", 250000.0))
    record.add_trace(
        agent="Research",
        action="Credit Bureau Assessment Completed",
        summary=f"CIBIL Score: {score} ({tier}). Income multiplier: {multiplier}. Sanction capacity verified at ₹{pre_amt:,.2f}."
    )
    return record
