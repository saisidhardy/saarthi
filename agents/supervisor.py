import time
import logging
from typing import Optional, Callable, Generator
from app.models import CaseFile
from app.database import save_case
from agents.intake import run_intake_agent
from agents.conversation import run_conversation_agent
from agents.negotiation import run_negotiation_agent
from agents.action import run_action_agent
from agents.compliance import run_compliance_agent
from agents.reporter import run_reporter_agent

logger = logging.getLogger("saarthi.supervisor")

def execute_step_with_retry(step_name: str, agent_fn: Callable[[CaseFile], CaseFile], case: CaseFile, max_retries: int = 3) -> CaseFile:
    retries = 0
    last_error = None
    while retries < max_retries:
        try:
            return agent_fn(case)
        except Exception as e:
            retries += 1
            last_error = e
            logger.warning(f"Error in {step_name} (attempt {retries}/{max_retries}): {e}")
            time.sleep(0.1)

    # Max retries exhausted -> Escalate to human
    case.status = "escalated"
    case.assigned_human = "System Exception Queue / Floor Supervisor"
    case.add_trace(
        agent="Supervisor",
        action=f"Step Failure Escalation: {step_name}",
        summary=f"Agent '{step_name}' failed after {max_retries} attempts: {last_error}. Escalated safely to human."
    )
    return case

def run_supervisor_pipeline(case: CaseFile, custom_borrower_reply: Optional[str] = None) -> CaseFile:
    """
    Deterministic State Machine Pipeline:
    Intake -> Conversation -> Negotiation -> Action -> Compliance -> Reporter
    """
    # 1. Intake
    case = execute_step_with_retry("Intake", run_intake_agent, case)
    save_case(case)

    # 2. Conversation
    conv_fn = lambda c: run_conversation_agent(c, custom_borrower_reply=custom_borrower_reply)
    case = execute_step_with_retry("Conversation", conv_fn, case)
    save_case(case)

    # 3. Negotiation
    case = execute_step_with_retry("Negotiation", run_negotiation_agent, case)
    save_case(case)

    # 4. Action
    case = execute_step_with_retry("Action", run_action_agent, case)
    save_case(case)

    # 5. Compliance
    case = execute_step_with_retry("Compliance", run_compliance_agent, case)
    save_case(case)

    # 6. Reporter
    case = execute_step_with_retry("Reporter", run_reporter_agent, case)
    save_case(case)

    return case

def run_supervisor_pipeline_stream(case: CaseFile, custom_borrower_reply: Optional[str] = None) -> Generator[CaseFile, None, None]:
    """
    Generator yielding the case file after each agent step for live SSE streaming to UI.
    """
    # 1. Intake
    case = execute_step_with_retry("Intake", run_intake_agent, case)
    save_case(case)
    yield case

    # 2. Conversation
    conv_fn = lambda c: run_conversation_agent(c, custom_borrower_reply=custom_borrower_reply)
    case = execute_step_with_retry("Conversation", conv_fn, case)
    save_case(case)
    yield case

    # 3. Negotiation
    case = execute_step_with_retry("Negotiation", run_negotiation_agent, case)
    save_case(case)
    yield case

    # 4. Action
    case = execute_step_with_retry("Action", run_action_agent, case)
    save_case(case)
    yield case

    # 5. Compliance
    case = execute_step_with_retry("Compliance", run_compliance_agent, case)
    save_case(case)
    yield case

    # 6. Reporter
    case = execute_step_with_retry("Reporter", run_reporter_agent, case)
    save_case(case)
    yield case
