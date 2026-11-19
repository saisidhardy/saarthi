import os
import yaml
import time
import logging
from typing import Optional, Dict, Any, Generator, List
from app.models import JourneyRecord, WorkflowDefinition, WorkflowStep, CaseFile
from app.database import save_case
from agents.registry import get_agent

logger = logging.getLogger("saarthi.engine")

WORKFLOWS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflows")

def load_workflow_definition(workflow_id: str = "collections") -> WorkflowDefinition:
    """
    Loads and parses a workflow YAML configuration.
    """
    yaml_path = os.path.join(WORKFLOWS_DIR, f"{workflow_id}.yaml")
    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"Workflow file not found: {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return WorkflowDefinition.model_validate(data)

def list_available_workflows() -> List[Dict[str, str]]:
    workflows = []
    if os.path.exists(WORKFLOWS_DIR):
        for f in os.listdir(WORKFLOWS_DIR):
            if f.endswith(".yaml") or f.endswith(".yml"):
                w_id = f.replace(".yaml", "").replace(".yml", "")
                try:
                    w_def = load_workflow_definition(w_id)
                    workflows.append({
                        "id": w_def.id,
                        "name": w_def.name,
                        "goal": w_def.goal,
                        "success_metric": w_def.success_metric
                    })
                except Exception as e:
                    logger.error(f"Error loading {f}: {e}")
    return workflows

def evaluate_condition(condition_str: Optional[str], record: JourneyRecord) -> bool:
    if not condition_str or not condition_str.strip():
        return True
    try:
        safe_builtins = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "len": len,
            "None": None,
            "True": True,
            "False": False
        }
        env = {
            "record": record,
            "data": record.data,
            "status": record.status,
            "intent": record.intent
        }
        return bool(eval(condition_str, {"__builtins__": safe_builtins}, env))
    except Exception as e:
        logger.warning(f"Condition eval error '{condition_str}': {e}. Defaulting to False.")
        return False

def run_step_with_retry(
    step: WorkflowStep,
    record: JourneyRecord,
    context: Dict[str, Any],
    custom_borrower_reply: Optional[str] = None
) -> JourneyRecord:
    agent_fn = get_agent(step.agent)
    retries = 0
    max_retries = step.retry_limit or 3
    last_error = None

    while retries < max_retries:
        try:
            # Check if agent accepts custom_borrower_reply (e.g. Conversation)
            if step.agent == "Conversation":
                return agent_fn(record, step=step, context=context, custom_borrower_reply=custom_borrower_reply)
            else:
                return agent_fn(record, step=step, context=context)
        except Exception as e:
            retries += 1
            last_error = e
            logger.warning(f"Step '{step.name}' attempt {retries}/{max_retries} failed: {e}")
            time.sleep(0.1)

    # Retry exhaustion handling
    if step.on_failure == "escalate":
        record.status = "escalated"
        record.assigned_human = "Workflow Exception Desk"
        record.add_trace(
            agent="Supervisor",
            action=f"Step Failure Escalation: {step.name}",
            summary=f"Step '{step.name}' failed after {max_retries} attempts: {last_error}. Escalated safely to human."
        )
    elif step.on_failure == "stop":
        record.status = "failed"
        record.add_trace(
            agent="Supervisor",
            action=f"Step Terminated: {step.name}",
            summary=f"Step '{step.name}' terminated workflow after {max_retries} failures: {last_error}."
        )
    else:
        record.add_trace(
            agent="Supervisor",
            action=f"Step Warning: {step.name}",
            summary=f"Step '{step.name}' failed but workflow continued: {last_error}."
        )

    return record

def check_human_escalation_rules(record: JourneyRecord, workflow: WorkflowDefinition):
    for rule in workflow.human_escalation_rules:
        if evaluate_condition(rule.condition, record) and record.status != "escalated":
            record.status = "escalated"
            record.assigned_human = rule.target_desk
            record.add_trace(
                agent="Supervisor",
                action="Human Escalation Rule Triggered",
                summary=f"Routed to {rule.target_desk}. Reason: {rule.reason}."
            )
            break

def run_supervisor_pipeline(
    record: JourneyRecord,
    workflow_id: Optional[str] = None,
    custom_borrower_reply: Optional[str] = None
) -> JourneyRecord:
    """
    Generic Workflow Supervisor Engine:
    Reads workflow YAML, runs ordered steps, applies conditional logic, retries, and escalation rules.
    """
    w_id = workflow_id or record.workflow_id or "collections"
    workflow = load_workflow_definition(w_id)
    record.workflow_id = workflow.id

    context = {
        "workflow_id": workflow.id,
        "policy_file": workflow.policy_file,
        "sample_data_file": workflow.sample_data_file
    }

    for step in workflow.steps:
        # Check condition
        if not evaluate_condition(step.condition, record):
            logger.info(f"Skipping step {step.name} due to condition: {step.condition}")
            continue

        record.stage = step.id
        record = run_step_with_retry(step, record, context, custom_borrower_reply=custom_borrower_reply)
        check_human_escalation_rules(record, workflow)
        save_case(record)

        if record.status in ("failed", "escalated") and step.on_failure == "stop":
            break

    return record

def run_supervisor_pipeline_stream(
    record: JourneyRecord,
    workflow_id: Optional[str] = None,
    custom_borrower_reply: Optional[str] = None
) -> Generator[JourneyRecord, None, None]:
    """
    Generator yielding the journey record after each step for real-time SSE streaming.
    """
    w_id = workflow_id or record.workflow_id or "collections"
    workflow = load_workflow_definition(w_id)
    record.workflow_id = workflow.id

    context = {
        "workflow_id": workflow.id,
        "policy_file": workflow.policy_file,
        "sample_data_file": workflow.sample_data_file
    }

    for step in workflow.steps:
        if not evaluate_condition(step.condition, record):
            continue

        record.stage = step.id
        record = run_step_with_retry(step, record, context, custom_borrower_reply=custom_borrower_reply)
        check_human_escalation_rules(record, workflow)
        save_case(record)
        yield record

        if record.status in ("failed", "escalated") and step.on_failure == "stop":
            break
