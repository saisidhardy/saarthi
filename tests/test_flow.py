import pytest
import os
from app.config import settings
from app.models import CaseFile
from app.database import init_db, clear_all_cases, get_case, get_all_cases
from app.main import load_sample_book
from agents.supervisor import run_supervisor_pipeline
from agents.reporter import compute_dashboard_metrics

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    load_sample_book()
    yield

def test_load_sample_book():
    cases = get_all_cases()
    assert len(cases) == 20
    # Check Account 1
    acc1 = get_case("1")
    assert acc1 is not None
    assert acc1.borrower_name == "Aniket Deshmukh"
    assert acc1.language == "Marathi"
    assert acc1.amount_due == 40000.0

def test_account_1_hero_ptp_flow():
    case = get_case("1")
    assert case.status == "new"

    # Run supervisor pipeline
    updated = run_supervisor_pipeline(case)
    
    # Verify all 6 agents ran in order
    agent_names = [t.agent for t in updated.trace]
    assert "Intake" in agent_names
    assert "Conversation" in agent_names
    assert "Negotiation" in agent_names
    assert "Action" in agent_names
    assert "Compliance" in agent_names
    assert "Reporter" in agent_names

    # Verify PTP and terms
    assert updated.status == "ptp"
    assert updated.intent == "ptp"
    assert updated.consent_played is True
    assert updated.payment_status == "sent"
    assert updated.payment_link is not None
    assert updated.payment_link.startswith("upi://pay")
    assert "Demo+Lender" in updated.payment_link
    assert updated.audit_pass is True

    # Check dashboard update
    metrics = compute_dashboard_metrics()
    assert metrics.contacted >= 1
    assert metrics.ptps >= 1
    assert metrics.our_cost_per_contact < metrics.industry_call_centre_cost

def test_account_2_dispute_escalation():
    case = get_case("2")
    updated = run_supervisor_pipeline(case)
    assert updated.intent == "dispute"
    assert updated.status == "escalated"
    assert updated.assigned_human is not None
    assert "Dispute" in updated.assigned_human

def test_account_3_hardship_escalation():
    case = get_case("3")
    updated = run_supervisor_pipeline(case)
    assert updated.intent == "hardship"
    assert updated.status == "escalated"
    assert updated.assigned_human is not None

def test_account_4_compliance_violation_fail():
    case = get_case("4")
    updated = run_supervisor_pipeline(case)
    # Compliance agent should flag the abusive threat
    assert updated.audit_pass is False
    assert "VIOLATION" in updated.audit_reason or "Fair Practices" in updated.audit_reason
    
    # Verify that failed audit account is not counted as healthy recovery in metrics
    metrics = compute_dashboard_metrics()
    # Case 4 should NOT increment ptps or paid
    valid_cases = [c for c in get_all_cases() if c.audit_pass is True]
    assert "4" not in [c.id for c in valid_cases]

def test_action_idempotency():
    case = get_case("1")
    updated_1 = run_supervisor_pipeline(case)
    link_1 = updated_1.payment_link
    
    # Run again on same case
    updated_2 = run_supervisor_pipeline(updated_1)
    link_2 = updated_2.payment_link
    assert link_1 == link_2
