import pytest
import os
from fastapi.testclient import TestClient
from app.config import settings
from app.models import JourneyRecord, CaseFile
from app.database import init_db, clear_all_cases, get_case, get_all_cases
from app.main import app, load_sample_book
from agents.supervisor import run_supervisor_pipeline, load_workflow_definition, set_global_pause
from agents.reporter import compute_engine_metrics
from services.sarvam import verify_sarvam_speakers_live, LANGUAGE_SPEAKER_MAP
from services.call_plan import generate_call_plan_from_csv, export_call_plan_csv, calculate_priority_score
from services.batch_audit import audit_batch_transcripts_csv, export_batch_audit_csv
from services.outcomes import analyze_outcomes_csv

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    set_global_pause(False)
    init_db()
    load_sample_book(workflow_id="collections")
    load_sample_book(workflow_id="loan_sales")
    yield
    set_global_pause(False)

# ==================== SCENARIO TESTS (S1 - S6) ====================

def test_load_sample_book():
    cases = get_all_cases("collections")
    assert len(cases) == 25
    acc1 = get_case("1", "collections")
    assert acc1 is not None
    assert acc1.customer_name == "Sunita Patil"
    assert acc1.language == "Marathi"
    assert acc1.amount_due == 40000.0

def test_s1_hero_ptp_flow():
    """
    S1 Hero (Marathi, Sunita Patil, Pune shop owner, Rs 40,000 EMI, DPD 3):
    Autopay bounce -> AI + recording disclosure -> identity check -> PTP on 5th -> 
    Compliance gate green -> simulate payment -> paid.
    """
    case = get_case("1", "collections")
    assert case.status == "new"

    updated = run_supervisor_pipeline(case, workflow_id="collections")
    
    agent_names = [t.agent for t in updated.trace]
    assert "Intake" in agent_names
    assert "Conversation" in agent_names
    assert "Negotiation" in agent_names
    assert "PolicyEngine" in agent_names
    assert "Compliance" in agent_names
    assert "Action" in agent_names
    assert "Reporter" in agent_names

    # Assert disclosures played
    assert updated.ai_disclosure_played is True
    assert updated.recording_disclosure_played is True
    assert updated.consent_played is True

    # Assert Policy Firewall
    firewall = updated.data.get("policy_firewall")
    assert firewall is not None
    assert firewall["status"] == "APPROVED"
    assert "POLICY-PTP" in firewall["rule_id"]

    # Assert Outcome
    assert updated.status == "ptp"
    assert updated.audit_pass is True

    # Since lender_vpa is unset in lender.yaml, payment_link is None and simulation is ready
    assert updated.payment_link is None
    assert updated.data.get("simulate_payment_only") is True

    # Test "Simulate payment" -> flips status to 'paid' (plain simulation)
    pay_res = client.post("/api/cases/1/simulate-payment?workflow_id=collections")
    assert pay_res.status_code == 200
    paid_case = pay_res.json()
    assert paid_case["status"] == "paid"
    assert paid_case["payment_status"] == "paid"

def test_s2_code_mixed_part_payment():
    """
    S2 Code-mixed part payment (Hindi/Hinglish):
    'Friday ko 2,500 bhar dunga, baaki next week'.
    Shows extracted structure: amount 2500, date resolved to ISO by CODE, intent part_payment.
    Engine approves since 2,500 >= 30% of ₹7,500.
    """
    case = get_case("2", "collections")
    updated = run_supervisor_pipeline(case, workflow_id="collections")
    
    assert updated.status == "ptp"
    assert updated.intent == "part_payment" or updated.data.get("llm_proposal", {}).get("intent") == "part_payment"
    
    # Understood chips
    chips = updated.data.get("understood_chips")
    assert chips is not None
    assert "2,500" in chips["amount"]
    
    # Policy Decision
    assert updated.data.get("policy_firewall")["status"] == "APPROVED"
    assert updated.audit_pass is True

def test_s4_sensitive_event_pause():
    """
    S4 Sensitive event:
    Borrower mentions father in hospital -> stops recovery conversation, no negotiation,
    no payment link, sets do_not_contact_until (7 days), human follow-up ticket: check insurance.
    """
    case = get_case("3", "collections")
    updated = run_supervisor_pipeline(case, workflow_id="collections")
    
    assert updated.status == "escalated"
    assert updated.assigned_human == "Sensitive Care & Compassionate Follow-up Desk"
    assert updated.do_not_contact_until is not None
    assert updated.payment_link is None  # NO payment link!
    
    firewall = updated.data.get("policy_firewall")
    assert firewall["status"] == "SENSITIVE_PAUSE"
    assert firewall["rule_id"] == "FAIR-PRAC-SENS01"
    assert "insurance" in updated.offer_made.lower()

def test_s7_preventive_bounce_rescue():
    """
    S7 T-24h Preventive Rescue:
    Intercepts low balance account 24h before debit, schedules remaining debit +3 days.
    """
    case = get_case("21", "collections")
    case.trigger_type = "PRE_DUE_T24H"
    updated = run_supervisor_pipeline(case, workflow_id="collections")
    
    assert updated.status == "ptp"
    assert updated.data["policy_firewall"]["rule_id"] == "POLICY-PREV-FEE01"
    assert updated.instant_recovered_inr == 6000.0
    assert updated.locked_mandate_inr == 12000.0

def test_s8_kirana_cashflow_micro_split():
    """
    S8 Kirana 4x Friday Micro-Split:
    Splits ₹40,000 into 4 tranches with mandate notice.
    """
    case = get_case("22", "collections")
    assert case is not None
    updated = run_supervisor_pipeline(case, workflow_id="collections")

    assert updated.status == "ptp"
    firewall = updated.data.get("policy_firewall")
    assert firewall is not None
    assert firewall["status"] == "APPROVED"
    assert firewall["rule_id"] == "POLICY-MICRO-SPLIT01"

    micro = updated.micro_schedule or updated.data.get("micro_schedule")
    assert micro is not None
    assert len(micro) == 4
    assert micro[0]["amount_inr"] == 10000.0
    assert micro[0]["rail"] == "UPI_NOW"
    assert micro[1]["rail"] == "UPI_AUTOPAY"
    assert "mandate request sent" in micro[1]["mandate_notice"]

def test_s3_adversarial_policy_firewall_block():
    case = get_case("4", "collections")
    updated = run_supervisor_pipeline(case, workflow_id="collections")
    
    assert updated.status == "escalated"
    assert updated.payment_link is None
    
    firewall = updated.data.get("policy_firewall")
    assert firewall is not None
    assert firewall["status"] == "BLOCKED"
    assert firewall["rule_id"] == "POLICY-WAIVER-NO01"
    assert "waiver" in firewall["engine_decided"].lower()

def test_s5_compliance_violation_fail():
    case = get_case("5", "collections")
    updated = run_supervisor_pipeline(case, workflow_id="collections")
    
    assert updated.audit_pass is False
    assert "VIOLATION" in updated.audit_reason
    assert updated.payment_link is None
    assert updated.assigned_human == "Chief Compliance Officer & Legal Desk"

def test_s6_audit_mode_samples():
    """
    S6 Audit Mode:
    Compliance agent returns a scorecard against YAML rules:
    Pass/fail per rule, triggering line, severity.
    """
    samples_res = client.get("/api/audit/samples")
    assert samples_res.status_code == 200
    samples = samples_res.json()
    assert "clean" in samples
    assert "abusive" in samples
    assert "emergency" in samples

    # 1. Clean call audit
    res_clean = client.post("/api/audit", json={"transcript": samples["clean"]["transcript"]})
    assert res_clean.status_code == 200
    report_clean = res_clean.json()
    assert report_clean["audit_pass"] is True
    assert report_clean["critical_violations_count"] == 0

    # 2. Abusive call audit
    res_abusive = client.post("/api/audit", json={"transcript": samples["abusive"]["transcript"]})
    assert res_abusive.status_code == 200
    report_abusive = res_abusive.json()
    assert report_abusive["audit_pass"] is False
    assert report_abusive["critical_violations_count"] >= 1

    # 3. Medical emergency violation audit
    res_emerg = client.post("/api/audit", json={"transcript": samples["emergency"]["transcript"]})
    assert res_emerg.status_code == 200
    report_emerg = res_emerg.json()
    assert report_emerg["audit_pass"] is False

def test_evidence_pack_retention_and_disclosures():
    case = get_case("1", "collections")
    run_supervisor_pipeline(case, workflow_id="collections")
    res = client.get("/api/cases/1/evidence-pack")
    assert res.status_code == 200
    pack = res.json()
    assert "evidence_pack_id" in pack
    assert "retention_until" in pack["telephony_meta"]
    assert pack["telephony_meta"]["policy_version"] == "2026.3-LENDER-APPROVED"
    assert pack["disclosures_played"]["ai_assistant_identity"] is True
    assert pack["disclosures_played"]["call_recording_notice"] is True
    assert "mandate" in pack["action_deliverables"]["mandate_notice"]
    assert "XXXXXX" in pack["phone"]  # Masked phone

def test_multi_lender_tenant_filtering():
    """
    Multi-lender tenancy:
    demo_lender_a: 10 accounts
    demo_lender_b: 9 accounts
    demo_lender_c: 6 accounts
    all: 25 accounts
    """
    r_a = client.get("/api/cases?lender_id=demo_lender_a")
    assert r_a.status_code == 200
    assert len(r_a.json()) == 10

    r_b = client.get("/api/cases?lender_id=demo_lender_b")
    assert r_b.status_code == 200
    assert len(r_b.json()) == 9

    r_c = client.get("/api/cases?lender_id=demo_lender_c")
    assert r_c.status_code == 200
    assert len(r_c.json()) == 6

    r_all = client.get("/api/cases?lender_id=all")
    assert r_all.status_code == 200
    assert len(r_all.json()) == 25

    # Check /api/lenders catalog
    l_res = client.get("/api/lenders")
    assert l_res.status_code == 200
    cat = l_res.json()
    assert "demo_lender_a" in cat
    assert "demo_lender_b" in cat
    assert "demo_lender_c" in cat
    assert "all" in cat

def test_call_plan_generator():
    """
    Part 2A: Call Plan generator dry run
    """
    csv_sample = """account_id,name,phone_masked,amount_due,dpd,language,preferred_time,prior_broken_ptps,sensitive_event,paid_today
ACC-01,Test User 1,+91 98XXX X0001,20000,10,Marathi,11:00 AM,0,n,n
ACC-02,Test User 2,+91 98XXX X0002,15000,5,Hindi,,0,y,n
ACC-03,Test User 3,+91 98XXX X0003,30000,15,Telugu,,0,n,y
ACC-04,Test User 4,+91 98XXX X0004,50000,25,English,,3,n,n
"""
    res = client.post("/api/call-plan/generate", json={"csv_content": csv_sample})
    assert res.status_code == 200
    plan = res.json()
    assert plan["summary"]["total_accounts"] == 4
    assert plan["summary"]["accounts_to_call"] == 1
    assert plan["summary"]["accounts_to_hold"] == 2
    assert plan["summary"]["accounts_to_escalate"] == 1
    assert plan["summary"]["cost_label"] == "estimated"

    # Test export CSV
    exp_res = client.get("/api/call-plan/export")
    assert exp_res.status_code == 200
    assert "text/csv" in exp_res.headers["content-type"]
    assert "priority_rank,account_id" in exp_res.text

def test_batch_audit_service():
    """
    Part 2B: Batch transcript audit and readiness checklist
    """
    res = client.post("/api/audit/batch", json={"csv_content": ""})
    assert res.status_code == 200
    data = res.json()
    assert "checklist" in data
    assert data["checklist"]["total_calls_audited"] == 4
    assert "POL-HARASS-01" in data["violations_by_rule"]
    assert len(data["violations"]) >= 1

    # Test export violations CSV
    exp_res = client.get("/api/audit/export")
    assert exp_res.status_code == 200
    assert "text/csv" in exp_res.headers["content-type"]
    assert "call_id,agent_id" in exp_res.text

def test_outcomes_import_service():
    """
    Part 2C: Outcome import and baseline comparison
    """
    res = client.post("/api/outcomes/import", json={"csv_content": ""})
    assert res.status_code == 200
    data = res.json()
    assert data["total_records"] == 10
    assert data["is_side_by_side"] is True
    assert "saarthi" in data["overall"]
    assert "baseline" in data["overall"]
    assert len(data["by_dpd_bucket"]) == 4

def test_verified_sarvam_speakers():
    """
    Part 1 Item 10: Verified Sarvam Bulbul:v3 speakers
    """
    res = client.get("/api/sarvam/live-status")
    assert res.status_code == 200
    data = res.json()
    mapping = data["speakers_mapping"]
    assert mapping["mr-IN"] == "rupali"
    assert mapping["hi-IN"] == "priya"
    assert mapping["te-IN"] == "shruti"
    assert mapping["ta-IN"] == "mani"
    assert mapping["kn-IN"] == "roopa"
    assert mapping["en-IN"] == "priya"
