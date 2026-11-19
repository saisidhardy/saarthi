from typing import Dict, Callable, Any
from app.models import JourneyRecord, WorkflowStep
from agents.intake import run_intake_agent
from agents.conversation import run_conversation_agent
from agents.decision import run_decision_agent
from agents.action import run_action_agent
from agents.compliance import run_compliance_agent
from agents.reporter import run_reporter_agent

# The Global Agent Registry (name -> function)
AGENT_REGISTRY: Dict[str, Callable[..., JourneyRecord]] = {
    "Intake": run_intake_agent,
    "Conversation": run_conversation_agent,
    "Decision": run_decision_agent,
    "Action": run_action_agent,
    "Compliance": run_compliance_agent,
    "Reporter": run_reporter_agent,
    # Backward compatibility alias
    "Negotiation": run_decision_agent
}

def get_agent(agent_name: str) -> Callable[..., JourneyRecord]:
    if agent_name not in AGENT_REGISTRY:
        raise ValueError(f"Agent '{agent_name}' not found in Agent Registry. Available agents: {list(AGENT_REGISTRY.keys())}")
    return AGENT_REGISTRY[agent_name]

def register_agent(name: str, fn: Callable[..., JourneyRecord]):
    AGENT_REGISTRY[name] = fn
