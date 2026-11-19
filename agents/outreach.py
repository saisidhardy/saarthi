from typing import Optional, Dict, Any
from app.models import JourneyRecord, WorkflowStep
from agents.conversation import run_conversation_agent
from agents.decision import run_decision_agent
from agents.action import run_action_agent
from agents.compliance import run_compliance_agent

def run_outreach_agent(
    record: JourneyRecord,
    step: Optional[WorkflowStep] = None,
    context: Optional[Dict[str, Any]] = None,
    custom_borrower_reply: Optional[str] = None
) -> JourneyRecord:
    """
    Outreach Agent:
    - Runs vernacular conversational call with customer consent
    - Evaluates customer negotiation response against sales policy
    - Audits compliance & TRAI standards
    - Dispatches digital sanction link & KYC document checklist via WhatsApp if qualified
    """
    # 1. Run Conversation
    record = run_conversation_agent(record, step=step, context=context, custom_borrower_reply=custom_borrower_reply)
    
    # 2. Re-evaluate customer response (handles custom rate negotiation / refusal)
    record = run_decision_agent(record, step=step, context=context)

    # 3. Compliance check
    record = run_compliance_agent(record, step=step, context=context)

    # 4. If qualified, dispatch WhatsApp application link and checklist
    if record.status == "qualified":
        record = run_action_agent(record, step=step, context=context)

    record.add_trace(
        agent="Outreach",
        action="Vernacular Outreach & Document Dispatch",
        summary=f"Outreach complete in {record.language}. Status: {record.status}. Offer: {record.data.get('offer_made')}."
    )
    return record
