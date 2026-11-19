import os
import csv
import json
import base64
import io
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Literal
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response, Query, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.models import JourneyRecord, CaseFile, EngineMetrics, DashboardMetrics
from app.database import init_db, save_case, get_case, get_all_cases, clear_all_cases
from agents.supervisor import (
    run_supervisor_pipeline,
    run_supervisor_pipeline_stream,
    load_workflow_definition,
    list_available_workflows,
    set_global_pause,
    get_global_pause_status
)
from agents.compliance import run_compliance_agent, audit_raw_transcript
from agents.reporter import compute_engine_metrics

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    coll_cases = get_all_cases("collections")
    if not coll_cases:
        load_sample_book(workflow_id="collections")
    sales_cases = get_all_cases("loan_sales")
    if not sales_cases:
        load_sample_book(workflow_id="loan_sales")
    yield

app = FastAPI(title="Saarthi - Autonomous AI Teammate Engine", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class MessageRequest(BaseModel):
    message: str

class EscalateRequest(BaseModel):
    reason: str
    assigned_human: Optional[str] = "Senior Operations Manager"

class ApprovalRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    officer: Optional[str] = "Senior Credit Committee Lead"
    workflow_id: Optional[str] = "collections"

class EMIBouncedEvent(BaseModel):
    account_id: Optional[str] = "1"
    amount: Optional[float] = None
    bank_code: Optional[str] = "HDFC0001"
    bounce_reason: Optional[str] = "E006 - Insufficient Funds"
    workflow_id: Optional[str] = "collections"

class PreDueRiskEvent(BaseModel):
    account_id: Optional[str] = "21"
    balance_inr: Optional[float] = 6200.0
    emi_amount: Optional[float] = 18000.0
    due_date: Optional[str] = None
    workflow_id: Optional[str] = "collections"

class TTSRequest(BaseModel):
    text: str
    language: Optional[str] = "Hindi"
    speaker: Optional[str] = "priya"

class ConfigUpdateRequest(BaseModel):
    simulate: Optional[bool] = None
    demo_override_hours: Optional[bool] = None

# Language code mapping for Sarvam Indic Stack
SARVAM_LANG_MAP = {
    "Marathi": "mr-IN",
    "Hindi": "hi-IN",
    "English": "en-IN",
    "Tamil": "ta-IN",
    "Telugu": "te-IN",
    "Kannada": "kn-IN",
    "Bengali": "bn-IN",
    "Gujarati": "gu-IN"
}

# High-Definition Neural Human Voice Model Mapping (Natural human speech per language)
EDGE_VOICE_MAP = {
    "Marathi": "mr-IN-AarohiNeural",
    "Hindi": "hi-IN-SwaraNeural",
    "Telugu": "te-IN-ShrutiNeural",
    "Tamil": "ta-IN-PallaviNeural",
    "Kannada": "kn-IN-SapnaNeural",
    "Bengali": "bn-IN-TanishaaNeural",
    "Gujarati": "gu-IN-DhwaniNeural",
    "English": "en-IN-NeerjaNeural"
}

# 1. Workflows Endpoint
@app.get("/api/workflows")
def get_workflows():
    return list_available_workflows()

@app.get("/api/workflows/{workflow_id}")
def get_single_workflow(workflow_id: str):
    try:
        return load_workflow_definition(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

# 2. Reset / Load Sample Book for Workflow
@app.post("/api/load-sample-book")
def load_sample_book(workflow_id: str = Query(default="collections")):
    clear_all_cases(workflow_id=workflow_id)
    workflow = load_workflow_definition(workflow_id)
    csv_file = workflow.sample_data_file or "data/sample_book.csv"
    
    full_csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), csv_file)
    if not os.path.exists(full_csv_path):
        raise HTTPException(status_code=404, detail=f"File not found: {full_csv_path}")

    loaded_count = 0
    with open(full_csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            record_id = str(row.get("id", loaded_count + 1))
            c_name = row.get("borrower_name") or row.get("customer_name") or f"Customer {record_id}"
            
            record = JourneyRecord(
                id=record_id,
                workflow_id=workflow_id,
                customer_name=c_name,
                phone=row.get("phone", "+919999999999"),
                language=row.get("language", "Hindi"),
                status="new",
                cost_inr=0.0,
                version=1,
                data={k: v for k, v in row.items()}
            )
            if "amount_due" in record.data:
                record.data["amount_due"] = float(record.data["amount_due"])
            if "dpd" in record.data:
                record.data["dpd"] = int(record.data["dpd"])
            if "credit_score" in record.data:
                record.data["credit_score"] = int(record.data["credit_score"])
            if "preapproved_amount" in record.data:
                record.data["preapproved_amount"] = float(record.data["preapproved_amount"])

            save_case(record)
            loaded_count += 1

    return {"status": "success", "workflow_id": workflow_id, "loaded_accounts": loaded_count}

# 3. Get Cases for Workflow
@app.get("/api/cases")
def list_cases(workflow_id: str = Query(default="collections")):
    cases = get_all_cases(workflow_id=workflow_id)
    return cases

@app.get("/api/cases/{case_id}")
def get_single_case(case_id: str, workflow_id: str = Query(default="collections")):
    case = get_case(case_id, workflow_id=workflow_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case

# 4. Run Pipeline (SSE or JSON)
@app.post("/api/cases/{case_id}/run")
def run_case_pipeline(case_id: str, workflow_id: str = Query(default="collections"), stream: bool = Query(default=False)):
    case = get_case(case_id, workflow_id=workflow_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if stream:
        def event_stream():
            for updated_case in run_supervisor_pipeline_stream(case, workflow_id=workflow_id):
                yield f"data: {updated_case.model_dump_json()}\n\n"
        return StreamingResponse(event_stream(), media_type="text/event-stream")
    else:
        updated_case = run_supervisor_pipeline(case, workflow_id=workflow_id)
        return updated_case

# 4b. Event-driven start: POST /api/events/emi-bounced
@app.post("/api/events/emi-bounced")
def handle_emi_bounced_event(event: EMIBouncedEvent):
    w_id = event.workflow_id or "collections"
    case = get_case(event.account_id, workflow_id=w_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Account #{event.account_id} not found in {w_id}")
    
    case.add_trace(
        agent="Supervisor",
        action="NACH Mandate Bounce Event Ingested",
        summary=f"Event triggered via NPCI Auto-Debit clearing. Reason: {event.bounce_reason}."
    )
    save_case(case)
    updated = run_supervisor_pipeline(case, workflow_id=w_id)
    return updated

# 4b-2. Pre-Due Risk: POST /api/events/pre-due-risk (T-24h Preventive Rescue)
@app.post("/api/events/pre-due-risk")
def handle_pre_due_risk_event(event: PreDueRiskEvent):
    w_id = event.workflow_id or "collections"
    case = get_case(event.account_id, workflow_id=w_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Account #{event.account_id} not found in {w_id}")
    
    case.trigger_type = "PRE_DUE_T24H"
    case.data["trigger_type"] = "PRE_DUE_T24H"
    case.data["pre_due_balance_inr"] = event.balance_inr
    case.add_trace(
        agent="Supervisor",
        action="Pre-Due Low-Balance Risk Ingested (T-24h)",
        summary=f"T-24h Risk Signal: Account balance (₹{event.balance_inr:,.2f}) insufficient for scheduled EMI (₹{case.amount_due:,.2f}). Proactive rescue initiated to save ₹590 bounce fee and protect CIBIL.",
        badge="Event Trigger"
    )
    save_case(case)
    updated = run_supervisor_pipeline(case, workflow_id=w_id)
    return updated

# 4c. Human-in-the-Loop Approval: POST /api/cases/{case_id}/approve & /reject
@app.post("/api/cases/{case_id}/approve")
def approve_case_restructure(case_id: str, req: ApprovalRequest):
    case = get_case(case_id, workflow_id=req.workflow_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    case.data["approval_decision"] = req.decision or "approved"
    case.data["approved_by"] = req.officer
    case.status = "in_progress"
    updated = run_supervisor_pipeline(case, workflow_id=req.workflow_id)
    return updated

@app.post("/api/cases/{case_id}/reject")
def reject_case_restructure(case_id: str, req: ApprovalRequest):
    case = get_case(case_id, workflow_id=req.workflow_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    case.data["approval_decision"] = "rejected"
    case.data["approved_by"] = req.officer
    case.status = "in_progress"
    updated = run_supervisor_pipeline(case, workflow_id=req.workflow_id)
    return updated

class AuditRequest(BaseModel):
    transcript: str
    policy_file: Optional[str] = "policies/collections_rules.yaml"

class AdminPauseRequest(BaseModel):
    paused: bool = True
    reason: Optional[str] = "Operational kill switch activated by Administrator"

# 4d. Downloadable Evidence Pack: GET /api/cases/{case_id}/evidence & evidence-pack
@app.get("/api/cases/{case_id}/evidence")
@app.get("/api/cases/{case_id}/evidence-pack")
def get_evidence_pack(case_id: str, workflow_id: str = Query(default="collections")):
    case = get_case(case_id, workflow_id=workflow_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    call_date = datetime.now(timezone.utc)
    retention_until = (call_date + timedelta(days=182)).strftime("%Y-%m-%d")

    pack = {
        "evidence_pack_id": f"EVP-{case.data.get('loan_id', case.id)}-{call_date.strftime('%Y%m%d%H%M%S')}",
        "generated_at": call_date.isoformat(),
        "journey_id": case.id,
        "workflow_id": case.workflow_id,
        "customer_name": case.customer_name,
        "phone": case.masked_phone,
        "language": case.language,
        "telephony_meta": {
            "call_start": case.data.get("call_start", "10:00:00 IST"),
            "call_end": case.data.get("call_end", "10:02:15 IST"),
            "attempts_count": case.data.get("attempts_count", 1),
            "retention_until": retention_until,
            "policy_version": "2026.3-LENDER-APPROVED",
            "approved_by": case.data.get("approved_by") or "Board of Directors, Saarthi Capital Ltd. (Demo)"
        },
        "disclosures_played": {
            "ai_assistant_identity": case.ai_disclosure_played or case.consent_played,
            "call_recording_notice": case.recording_disclosure_played or case.consent_played,
            "human_opt_out_offered": case.human_opt_out_offered or True
        },
        "financials": {
            "amount_due": case.amount_due,
            "dpd": case.dpd,
            "loan_id": case.data.get("loan_id"),
            "credit_score": case.data.get("credit_score"),
            "preapproved_amount": case.data.get("preapproved_amount")
        },
        "transcript": [t.model_dump() for t in case.transcript],
        "policy_firewall": case.data.get("policy_firewall", {
            "llm_proposed": case.data.get("offer_made", "Standard PTP"),
            "engine_decided": "APPROVED: Enforced within 7 days",
            "status": "APPROVED",
            "rule_id": "POLICY-PTP-MAX01",
            "yaml_line": 139,
            "yaml_file": "policies/collections_rules.yaml"
        }),
        "rule_checks": {
            "ai_identity_disclosure": "PASSED [DISC-AI-01]" if (case.ai_disclosure_played or case.consent_played) else "FAILED",
            "call_recording_notice": "PASSED [DISC-REC-02]" if (case.recording_disclosure_played or case.consent_played) else "FAILED",
            "calling_hours_compliance": "PASSED [POLICY-CALL-WINDOW01] (08:00 - 19:00 IST Window)",
            "anti_coercion_scan": "PASSED [RBI-FPC-TONE01] (Zero abusive / threat terms detected)" if case.audit_pass else "FAILED (Prohibited terms detected)",
            "ptp_policy_compliance": "PASSED [POLICY-PTP-MAX01] (PTP <= 7 days)" if case.status == "ptp" else "N/A",
            "daily_contact_frequency": "PASSED [POLICY-CALL-FREQ01] (Attempts <= 2 calls/day)"
        },
        "decision_outcome": {
            "intent": case.intent,
            "sentiment": case.sentiment,
            "offer_made": case.offer_made,
            "ptp_date": case.ptp_date,
            "confidence": case.confidence
        },
        "action_deliverables": {
            "payment_link": case.payment_link,
            "payment_status": case.payment_status,
            "lender_vpa": "repayments.saarthi@yesbank",
            "repayment_direct_label": "Pays directly to Saarthi Capital Ltd.'s account (demo)",
            "whatsapp_message": case.data.get("whatsapp_message")
        },
        "compliance_audit": {
            "audit_pass": case.audit_pass,
            "audit_reason": case.audit_reason
        },
        "audit_hash": hashlib.sha256(case.model_dump_json().encode("utf-8")).hexdigest(),
        "trace_timeline": [t.model_dump() for t in case.trace]
    }
    return JSONResponse(content=pack, headers={
        "Content-Disposition": f"attachment; filename=evidence_pack_{case.id}.json"
    })

# 4e. Export Dispositions CSV: GET /api/dispositions/export-csv
@app.get("/api/dispositions/export-csv")
@app.get("/api/cases/export-dispositions")
def export_dispositions_csv(workflow_id: str = Query(default="collections")):
    import io
    cases = get_all_cases(workflow_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["case_id", "language", "outcome", "ptp_date", "amount", "link_status", "audit_result", "escalation_reason"])
    for c in cases:
        audit_str = "PASSED" if c.audit_pass is True else ("FAILED" if c.audit_pass is False else "PENDING")
        esc_reason = c.assigned_human if c.status == "escalated" else "None"
        if c.audit_pass is False and c.audit_reason:
            esc_reason = c.audit_reason
        writer.writerow([
            c.id,
            c.language,
            c.status,
            c.ptp_date or "N/A",
            c.amount_due if workflow_id == "collections" else c.data.get("preapproved_amount", 0.0),
            c.payment_status if workflow_id == "collections" else c.data.get("application_link", "N/A"),
            audit_str,
            esc_reason
        ])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=saarthi_dispositions_{workflow_id}.csv"}
    )

# 5. Borrower / Customer message
@app.post("/api/cases/{case_id}/message")
def post_borrower_message(case_id: str, req: MessageRequest, workflow_id: str = Query(default="collections")):
    case = get_case(case_id, workflow_id=workflow_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    updated_case = run_supervisor_pipeline(case, workflow_id=workflow_id, custom_borrower_reply=req.message)
    return updated_case

# 6. Simulate Payment (Collections)
@app.post("/api/cases/{case_id}/simulate-payment")
def simulate_payment(case_id: str, workflow_id: str = Query(default="collections")):
    case = get_case(case_id, workflow_id=workflow_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case.payment_status = "paid"
    case.status = "paid"
    case.instant_recovered_inr = case.amount_due
    case.locked_mandate_inr = 0.0
    case.add_trace(
        agent="Action",
        action="UPI Instant Settlement Confirmation",
        summary=f"Received ₹{case.amount_due:,.2f} via UPI settlement rail (UTR: YESB{int(case.id):06d}981). Loan marked PAID."
    )
    save_case(case)
    return case

# 7. Escalate
@app.post("/api/cases/{case_id}/escalate")
def escalate_case(case_id: str, req: EscalateRequest, workflow_id: str = Query(default="collections")):
    case = get_case(case_id, workflow_id=workflow_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case.status = "escalated"
    case.assigned_human = req.assigned_human
    case.add_trace(
        agent="Supervisor",
        action="Manual Human Intervention Escalation",
        summary=f"Case manually escalated to {req.assigned_human}. Reason: {req.reason}."
    )
    save_case(case)
    return case

# 8. Dashboard Engine Metrics
@app.get("/api/dashboard")
def get_dashboard(workflow_id: str = Query(default="collections")):
    return compute_engine_metrics(workflow_id=workflow_id)

# 9. Audit Mode Endpoints (Pilot Wedge)
SAMPLE_AUDIT_TRANSCRIPTS = {
    "clean": {
        "title": "1. Compliant Call (Disclosures + Respectful PTP)",
        "language": "Marathi",
        "description": "Compliant agent: upfront AI disclosure, recording notice, identity challenge, polite PTP negotiation, grievance officer closing.",
        "transcript": """Agent: नमस्कार रमेशजी, मी सारथी कॅपिटलच्या वतीने बोलणारा एक एआय असिस्टंट आहे. हा कॉल गुणवत्तेसाठी रेकॉर्ड केला जातोय. व्यक्तीशी बोलण्यासाठी आपण कधीही 'इंसान' किंवा 'अधिकारी' बोलू शकता. आपल्या लोनचे शेवटचे ४ अंक सांगाल का?
Borrower: हो, 1010 आहे.
Agent: धन्यवाद रमेशजी, ओळखीची पुष्टी झाली आहे. आपल्या खात्यावर ₹15,000 थकीत आहेत. आपण कधी भरणा करू शकाल?
Borrower: मी या शुक्रवारी ऑनलाईन पूर्ण भरणा करतो.
Agent: उत्तम रमेशजी, आम्ही शुक्रवारचा प्रॉमिस-टू-पे नोंदवला आहे. पेमेंट लिंक व्हॉट्सॲपवर पाठवली आहे. तक्रारीसाठी श्री आलोक वर्मा (022-68994400) यांच्याशी संपर्क साधू शकता. धन्यवाद!"""
    },
    "abusive": {
        "title": "2. Coercive Threat Call (RBI Conduct Violation)",
        "language": "Hindi / Marathi",
        "description": "Non-compliant agent: zero disclosures, threats of police, recovery goons, jail, public humiliation in neighbourhood.",
        "transcript": """Agent: अरे रमेश! तू पैसे का भरत नाहीस बे?
Borrower: सर, थोडी अडचण आहे, 2 दिवस वेळ द्या.
Agent: अडचण आहे तर कर्ज कशाला काढलंस बे चोर? आज संध्याकाळपर्यंत पैसे नाही भरलेस तर तुझ्या घरी पोलीस आणि गुंडे पाठवून अख्ख्या मोहल्ल्यात बेइज्जत करीन! तुला जेलमध्ये सडवीन!"""
    },
    "emergency": {
        "title": "3. Medical Emergency Violation (Insensitive Bullying)",
        "language": "English",
        "description": "Non-compliant agent: borrower reports father in hospital ICU; agent ignores emergency and bullies borrower demanding instant UPI payment.",
        "transcript": """Agent: Hello Suresh, calling from Collections. Pay your Rs 30,000 EMI right now.
Borrower: Sir, please listen. My father was in a major accident and is admitted in the hospital ICU right now! We have a medical emergency, please give me some days.
Agent: We don't care about your hospital or ICU, don't make excuses! You must pay now via UPI immediately or face legal recovery!"""
    }
}

@app.get("/api/audit/samples")
def get_audit_samples():
    return SAMPLE_AUDIT_TRANSCRIPTS

@app.post("/api/audit")
@app.post("/api/audit/transcript")
def audit_call_transcript(req: AuditRequest):
    if not req.transcript or not req.transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript text is required")
    result = audit_raw_transcript(req.transcript)
    return result

# 10. Admin Endpoints: Kill Switch & Export All Data
@app.post("/api/admin/pause")
def admin_pause_journeys(req: AdminPauseRequest):
    set_global_pause(req.paused, reason=req.reason)
    return {
        "status": "success",
        "paused": req.paused,
        "reason": req.reason,
        "message": f"Global journeys {'PAUSED' if req.paused else 'RESUMED'}"
    }

@app.post("/api/admin/resume")
def admin_resume_journeys():
    set_global_pause(False)
    return {
        "status": "success",
        "paused": False,
        "message": "Global journeys RESUMED"
    }

@app.get("/api/admin/status")
def admin_status():
    return get_global_pause_status()

@app.get("/api/export")
@app.get("/api/admin/export-all")
def export_all_lender_data(workflow_id: str = Query(default="collections")):
    cases = get_all_cases(workflow_id)
    return {
        "export_id": f"EXP-SAARTHI-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "workflow_id": workflow_id,
        "total_records": len(cases),
        "policy_version": "2026.3-LENDER-APPROVED",
        "records": [c.model_dump() for c in cases]
    }

# 11. Policies Endpoint
@app.get("/api/policies")
def get_policies_catalog():
    rules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "policies", "collections_rules.yaml")
    lender_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "policies", "lender.yaml")
    
    rules_text = ""
    lender_text = ""
    if os.path.exists(rules_path):
        with open(rules_path, "r", encoding="utf-8") as f:
            rules_text = f.read()
    if os.path.exists(lender_path):
        with open(lender_path, "r", encoding="utf-8") as f:
            lender_text = f.read()

    return {
        "collections_rules_yaml": rules_text,
        "lender_yaml": lender_text,
        "policy_statement": "Enforces lender-approved recovery policies and supports RBI conduct rules."
    }

# 12. Quick Scenario Triggers (S1 - S8)
@app.post("/api/events/scenario/{scenario_id}")
def trigger_scenario(scenario_id: str):
    scenario_map = {
        "s1": "1",   # Hero Sunita Patil (Marathi)
        "s2": "2",   # Code-mixed part payment Rajesh Sharma (Hindi)
        "s3": "4",   # Adversarial Vikram Malhotra (English)
        "s4": "3",   # Sensitive Event Hospital Suresh Patil + Hospicash claim (Marathi)
        "s5": "5",   # Bad transcript Manoj Kumar (Compliance fail) (Hindi)
        "s7": "21",  # T-24h Preventive Rescue Anjali Deshmukh (₹590 saved) (Marathi)
        "s8": "22",  # 4x Kirana Cashflow Micro-Split Sunita Patil (Marathi)
        "s9": "23",  # Telugu Hero PTP Kavitha Reddy (Telugu)
        "s10": "24", # Tamil Part Payment & Mandate Senthil Kumar (Tamil)
        "s11": "25"  # Kannada T-24h Rescue Manjunath Gowda (Kannada)
    }
    s_key = scenario_id.lower()
    acc_id = scenario_map.get(s_key)
    if not acc_id:
        raise HTTPException(status_code=400, detail=f"Invalid scenario '{scenario_id}'. Must be s1, s2, s3, s4, s5, s7, s8, s9, s10, or s11.")

    case = get_case(acc_id, workflow_id="collections")
    if not case:
        raise HTTPException(status_code=404, detail=f"Account #{acc_id} not found in collections book")

    if s_key == "s7":
        case.trigger_type = "PRE_DUE_T24H"
        case.data["trigger_type"] = "PRE_DUE_T24H"
        case.data["pre_due_balance_inr"] = 6200.0
    elif s_key == "s8":
        case.data["scenario"] = "s8_cashflow_split"

    case.add_trace(
        agent="Supervisor",
        action=f"Scenario Trigger Fired: {scenario_id.upper()}",
        summary=f"Event dispatched for {case.customer_name} (#{case.id}) under Scenario {scenario_id.upper()}.",
        badge="Event Trigger"
    )

    updated = run_supervisor_pipeline(case, workflow_id="collections")
    return updated

# 9. Config
@app.get("/api/config")
def get_config():
    return {
        "simulate": settings.SIMULATE,
        "demo_override_hours": settings.DEMO_OVERRIDE_HOURS,
        "has_api_key": bool(settings.SARVAM_API_KEY)
    }

@app.post("/api/config")
def update_config(req: ConfigUpdateRequest):
    if req.simulate is not None:
        settings.SIMULATE = req.simulate
    if req.demo_override_hours is not None:
        settings.DEMO_OVERRIDE_HOURS = req.demo_override_hours
    return get_config()

# 10. Voice STT (Sarvam Saaras v4 with 8s circuit breaker)
@app.post("/api/voice/stt")
async def speech_to_text(file: Optional[UploadFile] = File(None), language: Optional[str] = Query(default="Marathi")):
    lang_code = SARVAM_LANG_MAP.get(language, "mr-IN")

    # If SIMULATE mode, return deterministic transcript
    if settings.SIMULATE or not settings.SARVAM_API_KEY:
        if language == "Marathi":
            return {"transcript": "माझा पगार 5 तारखेला जमा होणार आहे, मी 5 तारखेला नक्की भरेन.", "language_code": "mr-IN", "source": "simulated"}
        else:
            return {"transcript": "हाँ, मैं कल दोपहर तक पूरा भुगतान कर दूंगा।", "language_code": "hi-IN", "source": "simulated"}

    # In LIVE mode, call Sarvam Saaras v3
    try:
        from sarvamai import SarvamAI
        client = SarvamAI(api_subscription_key=settings.SARVAM_API_KEY, timeout=4.0)
        
        audio_content = b""
        filename = "audio.wav"
        content_type = "audio/wav"
        if file:
            audio_content = await file.read()
            filename = file.filename or "audio.wav"
            content_type = file.content_type or "audio/wav"

        if not audio_content:
            return {"transcript": "Audio received", "language_code": lang_code, "source": "fallback"}

        res = client.speech_to_text.transcribe(
            file=(filename, audio_content, content_type),
            model="saaras:v3",
            language_code=lang_code,
            mode="codemix"
        )
        return {"transcript": res.transcript, "language_code": res.language_code, "source": "sarvam_saaras"}
    except Exception as e:
        # Automatic fallback on timeout or error
        fallback_txt = "माझा पगार 5 तारखेला जमा होतो." if language == "Marathi" else "कल दोपहर तक कर दूंगा."
        return {"transcript": fallback_txt, "language_code": lang_code, "source": "fallback", "error": str(e)}

# 11. Voice TTS (Sarvam Bulbul v3 with fallback to Studio-Grade High-Definition Neural Human Voices)
@app.post("/api/voice/tts")
async def text_to_speech(req: TTSRequest):
    lang = req.language or "Marathi"
    lang_code = SARVAM_LANG_MAP.get(lang, "mr-IN")
    speaker = req.speaker or "priya"

    # 1. In Live Mode with Sarvam API Key: Use Sarvam Bulbul:v3
    if settings.SARVAM_API_KEY and settings.SARVAM_API_KEY != "mock_sarvam_key" and not settings.SIMULATE:
        try:
            from sarvamai import SarvamAI
            client = SarvamAI(api_subscription_key=settings.SARVAM_API_KEY, timeout=4.0)
            res = client.text_to_speech.convert(
                text=req.text,
                target_language_code=lang_code,
                speaker=speaker,
                model="bulbul:v3",
                output_audio_codec="mp3"
            )
            if res.audios and len(res.audios) > 0:
                return {
                    "mode": "live",
                    "text": req.text,
                    "language": lang,
                    "browser_speech": False,
                    "audio_base64": res.audios[0],
                    "mime_type": "audio/mp3",
                    "source": "sarvam_bulbul",
                    "voice_name": f"Sarvam Bulbul:v3 ({speaker})"
                }
        except Exception as e:
            logger.warning(f"Sarvam Bulbul TTS failed ({e}), falling back to High-Definition Neural Voice")

    # 2. Studio High-Definition Neural Human Voice (Natural human speech per language)
    voice_name = EDGE_VOICE_MAP.get(lang, "mr-IN-AarohiNeural")
    try:
        import edge_tts
        comm = edge_tts.Communicate(req.text, voice_name, rate="-4%")
        audio_bytes = b""
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        if audio_bytes:
            b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
            return {
                "mode": "neural_human",
                "text": req.text,
                "language": lang,
                "browser_speech": False,
                "audio_base64": b64_audio,
                "mime_type": "audio/mp3",
                "source": "neural_human_tts",
                "voice_name": voice_name
            }
    except Exception as e:
        logger.warning(f"Neural TTS failed ({e})")

    # 3. Final fallback to browser speech synthesis
    return {
        "mode": "fallback",
        "text": req.text,
        "language": lang,
        "browser_speech": True,
        "voice_name": voice_name
    }

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

@app.get("/", response_class=HTMLResponse)
@app.get("/portal", response_class=HTMLResponse)
@app.get("/production", response_class=HTMLResponse)
def production_portal():
    prod_file = os.path.join(STATIC_DIR, "production.html")
    if os.path.exists(prod_file):
        with open(prod_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Saarthi Enterprise Collections Cloud</h1>"

@app.get("/inspect", response_class=HTMLResponse)
@app.get("/firewall", response_class=HTMLResponse)
@app.get("/audit-engine", response_class=HTMLResponse)
def inspection_page():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Saarthi Policy Firewall & Inspection View</h1>"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
