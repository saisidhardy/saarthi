from typing import Optional, Dict, Any
from app.models import JourneyRecord, WorkflowStep

def run_human_approval_agent(
    record: JourneyRecord,
    step: Optional[WorkflowStep] = None,
    context: Optional[Dict[str, Any]] = None
) -> JourneyRecord:
    """
    Human-in-the-Loop Approval Step:
    - Triggers when restructuring or shortfall > ₹10,000
    - Pauses the journey in 'awaiting_approval' status
    - Awaits human supervisor action via POST /api/cases/{id}/approve
    """
    shortfall = float(record.data.get("shortfall_amount", 0.0))
    
    # If not yet decided by human, pause execution
    if record.data.get("approval_decision") is None:
        record.status = "awaiting_approval"
        record.data["approval_pending"] = True
        record.add_trace(
            agent="HumanApproval",
            action="Journey Paused for Senior Credit Authority Approval",
            summary=f"Shortfall ₹{shortfall:,.2f} exceeds ₹10,000 threshold. Journey paused awaiting floor manager sign-off."
        )
    else:
        decision = record.data.get("approval_decision")
        officer = record.data.get("approved_by", "Credit Officer")
        record.data["approval_pending"] = False
        
        if decision == "approved":
            record.status = "ptp"
            record.add_trace(
                agent="HumanApproval",
                action="Human Sign-Off Granted",
                summary=f"Restructure approved by {officer}. Shortfall ₹{shortfall:,.2f} sanctioned under exception matrix."
            )
        else:
            record.status = "escalated"
            record.assigned_human = officer
            record.add_trace(
                agent="HumanApproval",
                action="Human Sign-Off Declined",
                summary=f"Restructure rejected by {officer}. Routed to physical recovery queue."
            )

    return record
