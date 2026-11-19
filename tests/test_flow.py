import pytest
import os
from fastapi.testclient import TestClient
from app.config import settings
from app.models import JourneyRecord, CaseFile
from app.database import init_db, clear_all_cases, get_case, get_all_cases
from app.main import app, load_sample_book
from agents.supervisor import run_supervisor_pipeline, load_workflow_definition
from agents.reporter import compute_engine_metrics

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    load_sample_book(workflow_id="collections")
    load_sample_book(workflow_id="loan_sales")
    yield

# ==================== COLLECTIONS WORKFLOW TESTS ====================

def test_load_sample_book():
    cases = get_all_cases("collections")
    assert len(cases) == 20
    acc1 = get_case("1", "collections")
    assert acc1 is not None
    assert acc1.customer_name == "Sunita Patil"
    assert acc1.language == "Marathi"
    assert acc1.amount_due == 40000.0

def test_account_1_hero_ptp_flow():
    case = get_case("1", "collections")
    assert case.status == "new"

    updated = run_supervisor_pipeline(case, workflow_id="collections")
    
    agent_names = [t.agent for t in updated.trace]
    assert "Intake" in agent_names
    assert "Conversation" in agent_names
    assert "Decision" in agent_names
    assert "Action" in agent_names
    assert "Compliance" in agent_names
    assert "Reporter" in agent_names

    assert updated.status == "ptp"
    assert updated.intent == "ptp"
    assert updated.consent_played is True
    assert updated.payment_status == "sent"
    assert updated.payment_link is not None
    assert updated.payment_link.startswith("upi://pay")
    assert "Demo+Lender" in updated.payment_link
    assert updated.audit_pass is True

    metrics = compute_engine_metrics("collections")
    assert metrics.journeys_started >= 1
    assert metrics.journeys_completed_autonomously >= 1
    assert metrics.cost_per_completed_journey < metrics.industry_call_centre_cost

def test_account_2_part_payment_flow():
    case = get_case("2", "collections")
    updated = run_supervisor_pipeline(case, workflow_id="collections")
    assert updated.status == "ptp"
    assert updated.intent == "ptp"
    assert "Part-payment" in updated.offer_made
    assert updated.audit_pass is True
    assert updated.payment_status == "sent"

def test_account_6_dispute_escalation():
    case = get_case("6", "collections")
    updated = run_supervisor_pipeline(case, workflow_id="collections")
    assert updated.intent == "dispute"
    assert updated.status == "escalated"
    assert updated.assigned_human is not None
    assert "Dispute" in updated.assigned_human

def test_account_3_hardship_human_approval_pause():
    # Account 3 has shortfall > 10,000 -> should pause in 'awaiting_approval'
    case = get_case("3", "collections")
    updated = run_supervisor_pipeline(case, workflow_id="collections")
    assert updated.status == "awaiting_approval"
    assert updated.data.get("needs_approval") is True
    assert float(updated.data.get("shortfall_amount")) > 10000.0

    # Now simulate human approval via API
    res = client.post("/api/cases/3/approve", json={
        "decision": "approved",
        "officer": "Senior Credit Officer - Rohit S.",
        "workflow_id": "collections"
    })
    assert res.status_code == 200
    resumed = res.json()
    assert resumed["status"] == "ptp"
    assert "Human Sign-Off Granted" in [t["action"] for t in resumed["trace"]]

def test_account_4_compliance_violation_fail():
    case = get_case("4", "collections")
    updated = run_supervisor_pipeline(case, workflow_id="collections")
    assert updated.audit_pass is False
    assert "VIOLATION" in updated.audit_reason or "Fair Practices" in updated.audit_reason
    
    metrics = compute_engine_metrics("collections")
    valid_cases = [c for c in get_all_cases("collections") if c.audit_pass is True]
    assert "4" not in [c.id for c in valid_cases]

def test_account_5_identity_verification_fail():
    case = get_case("5", "collections")
    updated = run_supervisor_pipeline(case, workflow_id="collections")
    assert updated.status == "escalated"
    assert updated.data.get("identity_verified") is False
    assert updated.data.get("identity_failures") == 2
    assert "Identity" in updated.assigned_human or "Verification" in updated.assigned_human
    # Action must NEVER have run (no payment link generated)
    assert updated.payment_link is None

def test_action_idempotency():
    case = get_case("1", "collections")
    updated_1 = run_supervisor_pipeline(case, workflow_id="collections")
    link_1 = updated_1.payment_link
    
    updated_2 = run_supervisor_pipeline(updated_1, workflow_id="collections")
    link_2 = updated_2.payment_link
    assert link_1 == link_2

def test_event_driven_bounced_mandate():
    res = client.post("/api/events/emi-bounced", json={
        "account_id": "1",
        "workflow_id": "collections",
        "bounce_reason": "E006 - Insufficient Balance"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ptp"
    assert any("NACH Mandate Bounce" in t["action"] for t in data["trace"])

def test_download_evidence_pack():
    # Run pipeline on account 1 first
    case = get_case("1", "collections")
    run_supervisor_pipeline(case, workflow_id="collections")

    res = client.get("/api/cases/1/evidence-pack?workflow_id=collections")
    assert res.status_code == 200
    pack = res.json()
    assert "evidence_pack_id" in pack
    assert "audit_hash" in pack
    assert "transcript" in pack
    assert "rule_checks" in pack
    assert pack["rule_checks"]["calling_hours_compliance"] is not None
    assert pack["compliance_audit"]["audit_pass"] is True

def test_export_dispositions_csv():
    res = client.get("/api/dispositions/export-csv?workflow_id=collections")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    content = res.text
    assert "case_id,language,outcome,ptp_date,amount,link_status,audit_result,escalation_reason" in content
    assert "Sunita Patil" not in content  # CSV has case_id and outcome, not full names
    assert "1,Marathi" in content

# ==================== LOAN SALES WORKFLOW TESTS ====================

def test_loan_sales_load():
    leads = get_all_cases("loan_sales")
    assert len(leads) >= 8
    lead1 = get_case("1", "loan_sales")
    assert lead1.customer_name == "Swapnil Joshi"
    assert lead1.language == "Marathi"
    assert float(lead1.data.get("preapproved_amount")) == 350000.0

def test_loan_sales_lead_1_qualification():
    lead = get_case("1", "loan_sales")
    assert lead.status == "new"

    updated = run_supervisor_pipeline(lead, workflow_id="loan_sales")
    assert updated.status == "qualified"
    assert updated.data.get("application_link") is not None
    assert "apply.saarthi.demo" in updated.data.get("application_link")
    assert updated.data.get("docs_requested") is not None
    assert updated.audit_pass is True

    # Check 4 steps in trace: lead -> research -> offer -> outreach
    trace_agents = [t.agent for t in updated.trace]
    assert "Intake" in trace_agents
    assert "Research" in trace_agents
    assert "Decision" in trace_agents
    assert "Outreach" in trace_agents

def test_loan_sales_rate_negotiation_escalation():
    lead = get_case("3", "loan_sales")
    updated = run_supervisor_pipeline(lead, workflow_id="loan_sales")
    assert updated.status == "escalated"
    assert updated.assigned_human is not None
    assert "Relationship Manager" in updated.assigned_human
