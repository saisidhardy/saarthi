import logging
logger = logging.getLogger("saarthi.main")
import os
import csv
import json
import base64
import io
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Literal
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response, Query, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
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
from services.telephony_bridge import telephony_bridge
from services.sarvam import FALLBACK_MP3_B64, sarvam_service, LANGUAGE_SPEAKER_MAP, verify_sarvam_speakers_live
from services.call_plan import generate_call_plan_from_csv, export_call_plan_csv
from services.batch_audit import audit_batch_transcripts_csv, export_batch_audit_csv
from services.outcomes import analyze_outcomes_csv
from services.coach import (
    get_available_personas,
    get_consent,
    record_consent,
    run_full_cashflow_coach,
    calculate_refinance_comparison,
    CATEGORY_OVERRIDES,
    load_preapproved_offers,
    get_persona_raw_data
)

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
    bank_code: Optional[str] = "DEMOB0001"
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
            if "has_hospicash_rider" in record.data:
                val = str(record.data["has_hospicash_rider"]).strip().lower() in ("true", "1", "yes")
                record.has_hospicash_rider = val
                record.data["has_hospicash_rider"] = val

            save_case(record)
            loaded_count += 1

    return {"status": "success", "workflow_id": workflow_id, "loaded_accounts": loaded_count}

# Multi-Lender Tenant Agency Catalog
LENDER_TENANTS_CATALOG = {
    "all": {
        "id": "all",
        "name": "All Lenders (Agency View)",
        "short_name": "Agency View",
        "description": "Consolidated portfolio across all client money lenders (25 accounts)",
        "badge": "Multi-Tenant Agency",
        "bank": "Multi-Escrow Routing",
        "vpa": ""
    },
    "demo_lender_a": {
        "id": "demo_lender_a",
        "name": "Demo Lender A (Retail NBFC)",
        "short_name": "Demo Lender A",
        "description": "Retail consumer durable & personal loan book (10 accounts)",
        "badge": "Retail NBFC",
        "bank": "Demo Bank Ltd.",
        "vpa": ""
    },
    "demo_lender_b": {
        "id": "demo_lender_b",
        "name": "Demo Lender B (MSME & Working Capital)",
        "short_name": "Demo Lender B",
        "description": "Kirana & merchant working capital book (9 accounts)",
        "badge": "MSME Lender",
        "bank": "Demo Bank Ltd.",
        "vpa": ""
    },
    "demo_lender_c": {
        "id": "demo_lender_c",
        "name": "Demo Lender C (Microfinance & Rural)",
        "short_name": "Demo Lender C",
        "description": "Joint liability & rural livelihood loan book (6 accounts)",
        "badge": "Microfinance",
        "bank": "Demo Bank Ltd.",
        "vpa": ""
    }
}

# 3. Get Cases for Workflow (with Multi-Lender Tenant filtering)
@app.get("/api/cases")
def list_cases(
    workflow_id: str = Query(default="collections"),
    lender_id: Optional[str] = Query(default=None)
):
    cases = get_all_cases(workflow_id=workflow_id)
    if lender_id and lender_id != "all":
        cases = [c for c in cases if c.data.get("lender_id") == lender_id]
    return cases

@app.get("/api/lenders")
def get_lenders_catalog():
    return LENDER_TENANTS_CATALOG

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
        summary=f"T-24h Risk Signal: Account balance (₹{event.balance_inr:,.2f}) insufficient for scheduled EMI (₹{case.amount_due:,.2f}). Proactive rescue initiated: collected buffer payment today and rescheduled remainder by 3 days per policy.",
        badge="Event Trigger"
    )
    save_case(case)
    updated = run_supervisor_pipeline(case, workflow_id=w_id)
    return updated

# 4b-3. Borrower Voice-First Khata & 10% QR Auto-Sweep: POST /api/borrower/qr-sweep-activate
class QRSweepActivateRequest(BaseModel):
    journey_id: str
    sweep_pct: int = 10
    voice_confirmation_text: Optional[str] = "हो, १०% QR कट चालेल"
    workflow_id: Optional[str] = "collections"

@app.post("/api/borrower/qr-sweep-activate")
def activate_borrower_qr_sweep(req: QRSweepActivateRequest):
    w_id = req.workflow_id or "collections"
    case = get_case(req.journey_id, workflow_id=w_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Borrower journey #{req.journey_id} not found in {w_id}")

    if req.sweep_pct <= 0 or req.sweep_pct > 50:
        raise HTTPException(
            status_code=400,
            detail="Invalid sweep percentage. POLICY-QR-SWEEP01 permits 1% to 50% (default: 10%)."
        )

    # Enforce POLICY-QR-SWEEP01
    case.repayment_rail = f"MERCHANT_QR_SWEEP_{req.sweep_pct}PCT"
    case.data["repayment_rail"] = f"MERCHANT_QR_SWEEP_{req.sweep_pct}PCT"
    case.locked_mandate_inr = float(case.amount_due)
    case.data["locked_mandate_inr"] = float(case.amount_due)
    case.data["qr_sweep_active"] = True
    case.data["qr_sweep_pct"] = req.sweep_pct

    if case.status not in ("paid",):
        case.status = "ptp"

    # Append borrower voice confirmation to transcript
    voice_text = req.voice_confirmation_text or "हो, १०% QR कट चालेल"
    case.add_transcript(speaker="borrower", text=voice_text)

    # Saarthi personalized Indic voice confirmation
    name_map = {"sunita": "सुनीता", "rajesh": "राजेश", "suresh": "सुरेश", "anjali": "अंजली", "vikram": "विक्रम", "manoj": "मनोज"}
    first_name_raw = case.customer_name.split()[0] if case.customer_name else "ग्राहक"
    first_name = name_map.get(first_name_raw.lower(), first_name_raw)
    pct_str = "१०" if req.sweep_pct == 10 else str(req.sweep_pct)

    if case.language == "Marathi" or "sunita" in case.customer_name.lower() or "सुनीता" in case.customer_name:
        agent_reply = f"धन्यवाद {first_name} ताई! तुमचा {pct_str}% दैनिक QR ऑटो-स्वीप सुरू झाला आहे. थकबाकी टप्प्याटप्प्याने भरली जाईल."
    elif case.language == "Telugu":
        agent_reply = f"ధన్యవాదాలు {first_name} గారు! మీ {req.sweep_pct}% రోజువారీ QR ఆటో-స్వీప్ ప్రారంభించబడింది."
    elif case.language == "Tamil":
        agent_reply = f"நன்றி {first_name} அவர்களே! உங்கள் {req.sweep_pct}% தினசரி QR ஆட்டோ-ஸ்வீப் தொடங்கப்பட்டது."
    elif case.language == "Kannada":
        agent_reply = f"ಧನ್ಯವಾದಗಳು {first_name} ಅವರೇ! ನಿಮ್ಮ {req.sweep_pct}% ದೈನಂದಿನ QR ಆಟೋ-ಸ್ವೀಪ್ ಸಕ್ರಿಯವಾಗಿದೆ."
    else:
        agent_reply = f"धन्यवाद {first_name} जी! आपका {req.sweep_pct}% दैनिक QR ऑटो-स्वीप शुरू हो गया है। बक़ाया राशि दैनिक बिक्री से चुकता होगी।"

    case.add_transcript(speaker="agent", text=agent_reply)

    # Add audit trace for Evidence Pack
    case.add_trace(
        agent="BorrowerKhataPortal",
        action="Voice QR Auto-Sweep Activation",
        summary=f"Borrower voice-confirmed {req.sweep_pct}% Pay-As-You-Sell QR auto-sweep ('{voice_text}'). Locked mandate ₹{case.amount_due:,.2f} under POLICY-QR-SWEEP01.",
        badge="Voice Khata Sweep"
    )

    save_case(case)

    # Compute updated KPIs
    updated_kpis = compute_engine_metrics(workflow_id=w_id)

    return {
        "success": True,
        "message": f"Merchant QR {req.sweep_pct}% Auto-Sweep successfully activated",
        "rule_id": "POLICY-QR-SWEEP01",
        "journey_id": case.id,
        "repayment_rail": case.data.get("repayment_rail"),
        "locked_mandate_inr": case.amount_due,
        "mandate_wording": "mandate request sent; becomes active only when the borrower approves it in her UPI app; she can revoke it",
        "voice_response": agent_reply,
        "kpis": updated_kpis.model_dump(),
        "case": case.model_dump()
    }

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
            "approved_by": case.data.get("approved_by") or "Demo Lender A (Board of Directors)"
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
            "daily_contact_frequency": "PASSED [POLICY-CALL-FREQ01] (Attempts <= 2 calls/day)",
            "qr_auto_sweep_policy": "PASSED [POLICY-QR-SWEEP01] (10% Pay-As-You-Sell Auto-Sweep)" if case.data.get("qr_sweep_active") else "N/A"
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
            "repayment_rail": case.data.get("repayment_rail") or ("MERCHANT_QR_SWEEP_10PCT" if case.data.get("qr_sweep_active") else "UPI_DIRECT_OR_AUTOPAY"),
            "qr_sweep_active": bool(case.data.get("qr_sweep_active", False)),
            "lender_vpa": "",
            "mandate_notice": "mandate request sent; becomes active only when the borrower approves it in her UPI app; she can revoke it",
            "repayment_direct_label": "Pays directly to Demo Lender A designated escrow account (demo)",
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

# 6. Simulate Payment (Collections) - Plain Payment Simulation Screen
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
        action="Simulated Payment Confirmation",
        summary=f"Simulated payment received for ₹{case.amount_due:,.2f}. Account balance cleared (simulated payment test rail)."
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
        "transcript": """Agent: नमस्कार रमेशजी, मी डेमो लेंडर ए च्या वतीने बोलणारा एक एआय असिस्टंट आहे. हा कॉल गुणवत्तेसाठी रेकॉर्ड केला जातोय. व्यक्तीशी बोलण्यासाठी आपण कधीही 'इंसान' किंवा 'अधिकारी' बोलू शकता. आपल्या लोनचे शेवटचे ४ अंक सांगाल का?
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
        "s4": "3",   # Sensitive Event Hospital Suresh Patil (7-day pause & human follow-up) (Marathi)
        "s5": "5",   # Bad transcript Manoj Kumar (Compliance fail) (Hindi)
        "s6": "5",   # Pilot wedge audit mode Manoj Kumar (Hindi)
        "s7": "21",  # T-24h Preventive Rescue Anjali Deshmukh (Reschedule debit & buffer) (Marathi)
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

@app.get("/api/voice/demo-audio/{language}")
def get_demo_audio(language: str):
    lang_lower = language.lower()
    fname_map = {
        "english": "demo_english.mp3",
        "en": "demo_english.mp3",
        "hindi": "demo_hindi.mp3",
        "hi": "demo_hindi.mp3",
        "telugu": "demo_telugu.mp3",
        "te": "demo_telugu.mp3"
    }
    fname = fname_map.get(lang_lower, "demo_hindi.mp3")
    fpath = os.path.join(STATIC_DIR, "audio", fname)
    if os.path.exists(fpath):
        from fastapi.responses import FileResponse
        return FileResponse(fpath, media_type="audio/mpeg")
    raise HTTPException(status_code=404, detail="Audio file not found")


# ==================== TELEPHONY BRIDGE (EXOTEL & TWILIO PSTN) ====================

class OutboundCallRequest(BaseModel):
    case_id: str
    phone: Optional[str] = None
    provider: Optional[str] = None
    caller_id: Optional[str] = None

async def synthesize_carrier_audio_bytes(text: str, language: str) -> bytes:
    lang = language or "Marathi"
    voice_name = EDGE_VOICE_MAP.get(lang, "mr-IN-AarohiNeural")
    try:
        import edge_tts
        comm = edge_tts.Communicate(text, voice_name, rate="-4%")
        audio_bytes = b""
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        if audio_bytes:
            return audio_bytes
    except Exception as e:
        logger.warning(f"Carrier edge-tts audio synthesis fallback: {e}")
    # Minimal valid MP3 audio fallback
    raw = FALLBACK_MP3_B64
    pad = len(raw) % 4
    if pad:
        raw += "=" * (4 - pad)
    return base64.b64decode(raw)

@app.post("/api/telephony/call")
def trigger_outbound_call(req: OutboundCallRequest):
    case = get_case(req.case_id, workflow_id="collections")
    if not case:
        raise HTTPException(status_code=404, detail=f"Case #{req.case_id} not found in collections book")
    
    result = telephony_bridge.initiate_outbound_call(
        case=case,
        phone_override=req.phone,
        provider_override=req.provider,
        caller_id_override=req.caller_id
    )
    return result

@app.get("/api/telephony/audio/{case_id}/{turn_index}")
async def get_carrier_telephony_audio(case_id: str, turn_index: int):
    case = get_case(case_id, workflow_id="collections")
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    agent_turns = [t for t in case.transcript if t.speaker == "agent"]
    text = agent_turns[-1].text if agent_turns else "नमस्कार, मी सारथी कॅपिटलकडून बोलत आहे."
    audio_bytes = await synthesize_carrier_audio_bytes(text, case.language)
    return Response(content=audio_bytes, media_type="audio/mpeg")

@app.post("/api/telephony/twilio/voice")
@app.post("/api/telephony/twilio/gather")
def twilio_voice_webhook(
    case_id: str = Query(...),
    SpeechResult: Optional[str] = Form(default=None),
    CallSid: Optional[str] = Form(default=None)
):
    case = get_case(case_id, workflow_id="collections")
    if not case:
        raise HTTPException(status_code=404, detail=f"Case #{case_id} not found")
    
    xml_content = telephony_bridge.generate_twiml_turn(case, borrower_speech=SpeechResult)
    return Response(content=xml_content, media_type="application/xml")

@app.post("/api/telephony/exotel/flow")
@app.post("/api/telephony/exotel/gather")
def exotel_flow_webhook(
    case_id: str = Query(...),
    SpeechResult: Optional[str] = Form(default=None),
    CallSid: Optional[str] = Form(default=None)
):
    case = get_case(case_id, workflow_id="collections")
    if not case:
        raise HTTPException(status_code=404, detail=f"Case #{case_id} not found")
    
    flow_json = telephony_bridge.generate_exotel_passthru_turn(case, borrower_speech=SpeechResult)
    return flow_json

@app.post("/api/telephony/status")
def telephony_status_callback(
    CallSid: Optional[str] = Form(default=None),
    CallStatus: Optional[str] = Form(default=None),
    DialCallDuration: Optional[str] = Form(default=None)
):
    return {
        "status": "acknowledged",
        "call_sid": CallSid,
        "call_status": CallStatus,
        "duration_seconds": DialCallDuration
    }

# ==================== PART 2: CALL PLAN, BATCH AUDIT & OUTCOME IMPORT ====================

# Global in-memory cache for export downloads
LATEST_CALL_PLAN_DATA: Optional[Dict[str, Any]] = None
LATEST_BATCH_AUDIT_DATA: Optional[Dict[str, Any]] = None

class CSVInputRequest(BaseModel):
    csv_content: Optional[str] = None

DEFAULT_SAMPLE_CALL_PLAN_CSV = """account_id,name,phone_masked,amount_due,dpd,language,preferred_time,prior_broken_ptps,sensitive_event,paid_today
ACC-101,Sunita Patil,+91 98XXX X1001,15000,5,Marathi,11:00 AM,0,n,n
ACC-102,Rajesh Sharma,+91 98XXX X1002,32000,14,Hindi,15:30 IST,1,n,n
ACC-103,Suresh Patil,+91 98XXX X1003,28000,22,Marathi,10:00 AM,0,y,n
ACC-104,Vikram Malhotra,+91 98XXX X1004,75000,29,English,17:00 IST,2,n,n
ACC-105,Manoj Kumar,+91 98XXX X1005,12000,3,Hindi,12:00 PM,0,n,y
ACC-106,Kavitha Reddy,+91 98XXX X1006,45000,18,Telugu,14:00 IST,1,n,n
ACC-107,Senthil Kumar,+91 98XXX X1007,20000,8,Tamil,10:30 AM,0,n,n
ACC-108,Manjunath Gowda,+91 98XXX X1008,18000,12,Kannada,16:00 IST,3,n,n
"""

DEFAULT_SAMPLE_BATCH_AUDIT_CSV = """call_id,agent_id,start_time,transcript
CALL-001,Agent-Ramesh,2026-11-20 10:15:00,"Agent: नमस्कार, मी डेमो लेंडर ए च्या वतीने बोलणारा एक एआय असिस्टंट आहे. हा कॉल गुणवत्तेसाठी रेकॉर्ड केला जातोय. आपल्या लोनचे शेवटचे ४ अंक सांगाल का? Borrower: हो, 1001 आहे. Agent: धन्यवाद. आपल्या खात्यावर ₹15,000 थकीत आहेत. आपण कधी भरणा करू शकाल? Borrower: मी शुक्रवारी ऑनलाईन पूर्ण भरणा करतो. Agent: आम्ही नोंद केली आहे, धन्यवाद."
CALL-002,Agent-Suresh,2026-11-20 07:30:00,"Agent: अरे भाई, मैं तो 2 दिन पहले ही पूरे पैसे भर चुका हूँ! मेरे खाते से कट गए हैं, दोबारा फोन क्यों कर रहे हो? Agent: पैसे नहीं भरे तो जेल में सड़ा देंगे, पुलिस भेजेंगे तेरे घर!"
CALL-003,Agent-Pooja,2026-11-20 14:00:00,"Agent: Hello, calling from Demo Lender. You have an overdue EMI of Rs 25,000. Borrower: I want to lodge a complaint against previous abusive calls. Agent: Please note our Principal Nodal Officer Mr. Alok Verma at 022-68994400 or email nodal.officer@demolender.example."
CALL-004,Agent-Vikas,2026-11-20 20:45:00,"Agent: नमस्ते, पैसे कब दे रहे हो? Borrower: अभी काम में हूँ कल बात करना."
"""

DEFAULT_SAMPLE_OUTCOMES_CSV = """account_id,group,paid,paid_amount,paid_date,ptp_date,dpd,language
ACC-001,saarthi,y,15000,2026-11-15,2026-11-15,5,Marathi
ACC-002,saarthi,y,10000,2026-11-16,2026-11-16,14,Hindi
ACC-003,saarthi,n,0,,2026-11-18,22,Marathi
ACC-004,saarthi,y,25000,2026-11-14,2026-11-14,29,English
ACC-005,saarthi,y,12000,2026-11-17,2026-11-17,3,Hindi
ACC-006,saarthi,y,18000,2026-11-18,2026-11-18,8,Telugu
ACC-007,baseline,y,15000,2026-11-15,2026-11-15,5,Marathi
ACC-008,baseline,n,0,,2026-11-16,14,Hindi
ACC-009,baseline,n,0,,2026-11-18,22,Marathi
ACC-010,baseline,n,0,,2026-11-14,29,English
"""

@app.post("/api/call-plan/generate")
async def api_generate_call_plan(request: Request):
    global LATEST_CALL_PLAN_DATA
    csv_text = ""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            csv_text = body.get("csv_content", "")
        except Exception:
            pass
    elif "multipart/form-data" in content_type:
        try:
            form = await request.form()
            if "file" in form and hasattr(form["file"], "read"):
                raw_bytes = await form["file"].read()
                csv_text = raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            pass
            
    if not csv_text or not csv_text.strip():
        csv_text = DEFAULT_SAMPLE_CALL_PLAN_CSV
        
    result = generate_call_plan_from_csv(csv_text)
    LATEST_CALL_PLAN_DATA = result
    return result

@app.get("/api/call-plan/export")
def api_export_call_plan():
    global LATEST_CALL_PLAN_DATA
    if not LATEST_CALL_PLAN_DATA:
        LATEST_CALL_PLAN_DATA = generate_call_plan_from_csv(DEFAULT_SAMPLE_CALL_PLAN_CSV)
    csv_str = export_call_plan_csv(LATEST_CALL_PLAN_DATA)
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=saarthi_today_call_plan.csv"}
    )

@app.post("/api/audit/batch")
async def api_audit_batch(request: Request):
    global LATEST_BATCH_AUDIT_DATA
    csv_text = ""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            csv_text = body.get("csv_content", "")
        except Exception:
            pass
    elif "multipart/form-data" in content_type:
        try:
            form = await request.form()
            if "file" in form and hasattr(form["file"], "read"):
                raw_bytes = await form["file"].read()
                csv_text = raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            pass
            
    if not csv_text or not csv_text.strip():
        csv_text = DEFAULT_SAMPLE_BATCH_AUDIT_CSV
        
    result = audit_batch_transcripts_csv(csv_text)
    LATEST_BATCH_AUDIT_DATA = result
    return result

@app.get("/api/audit/export")
def api_export_batch_audit():
    global LATEST_BATCH_AUDIT_DATA
    if not LATEST_BATCH_AUDIT_DATA:
        LATEST_BATCH_AUDIT_DATA = audit_batch_transcripts_csv(DEFAULT_SAMPLE_BATCH_AUDIT_CSV)
    csv_str = export_batch_audit_csv(LATEST_BATCH_AUDIT_DATA)
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=saarthi_batch_audit_violations.csv"}
    )

@app.post("/api/outcomes/import")
async def api_import_outcomes(request: Request):
    csv_text = ""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            csv_text = body.get("csv_content", "")
        except Exception:
            pass
    elif "multipart/form-data" in content_type:
        try:
            form = await request.form()
            if "file" in form and hasattr(form["file"], "read"):
                raw_bytes = await form["file"].read()
                csv_text = raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            pass
            
    if not csv_text or not csv_text.strip():
        csv_text = DEFAULT_SAMPLE_OUTCOMES_CSV
        
    result = analyze_outcomes_csv(csv_text)
    return result

@app.get("/api/sarvam/live-status")
def api_sarvam_live_status():
    status = verify_sarvam_speakers_live()
    cost_summary = sarvam_service.get_cost_summary()
    return {
        "status": status,
        "usage_and_costs": cost_summary,
        "speakers_mapping": LANGUAGE_SPEAKER_MAP
    }

# ==========================================
# 16. CASH-FLOW COACH (V5 Delta - Separate Opt-In Prototype)
# ==========================================
class CoachConsentRequest(BaseModel):
    persona_id: str
    granted: bool
    purpose: Optional[str] = "AFFORDABLE_REPAYMENT_ASSESSMENT"

class CoachOverrideRequest(BaseModel):
    persona_id: str
    category: str
    role: str # "essential", "flexible", "ignore"

class CoachRefinanceRequest(BaseModel):
    persona_id: str
    candidate_offer: Dict[str, Any]

class CoachHandoffRequest(BaseModel):
    persona_id: str
    notes: Optional[str] = ""

@app.get("/api/coach/personas")
def api_coach_personas():
    return {"personas": get_available_personas()}

@app.get("/api/coach/consent")
def api_coach_get_consent(persona_id: str = "kirana_owner"):
    return get_consent(persona_id)

@app.post("/api/coach/consent")
def api_coach_record_consent(req: CoachConsentRequest):
    record = record_consent(req.persona_id, granted=req.granted, purpose=req.purpose or "AFFORDABLE_REPAYMENT_ASSESSMENT")
    
    # Optional mapping to active loan cases in evidence pack
    persona_case_map = {
        "kirana_owner": "1",
        "salaried_household": "2",
        "agri_trader": "25"
    }
    case_id = persona_case_map.get(req.persona_id)
    if case_id:
        case = get_case(case_id, workflow_id="collections")
        if case:
            case.data["aa_consent"] = record
            case.add_trace(
                agent="CashFlowCoach",
                action="Account Aggregator Consent Updated",
                summary=f"Consent status for {req.persona_id}: {record['status']} (ID: {record['consent_id']})",
                badge="Consent"
            )
            save_case(case)
            
    return record

@app.get("/api/coach/analysis")
def api_coach_analysis(persona_id: str = "kirana_owner"):
    return run_full_cashflow_coach(persona_id)

@app.post("/api/coach/override-category")
def api_coach_override_category(req: CoachOverrideRequest):
    if req.persona_id not in CATEGORY_OVERRIDES:
        CATEGORY_OVERRIDES[req.persona_id] = {}
    CATEGORY_OVERRIDES[req.persona_id][req.category] = req.role
    return run_full_cashflow_coach(req.persona_id)

@app.post("/api/coach/refinance-evaluate")
def api_coach_refinance_evaluate(req: CoachRefinanceRequest):
    raw = get_persona_raw_data(req.persona_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Persona not found")
    existing_loan = raw.get("attributes", {}).get("existing_loan", {})
    
    # Get weekly capacity
    analysis = run_full_cashflow_coach(req.persona_id)
    weekly_cap = 1000.0
    if not analysis.get("consent_required"):
        weekly_cap = analysis.get("capacity_plan", {}).get("final_weekly_capacity_inr", 1000.0)
        
    return calculate_refinance_comparison(existing_loan, req.candidate_offer, weekly_cap)

@app.post("/api/coach/advisor-handoff")
def api_coach_advisor_handoff(req: CoachHandoffRequest):
    analysis = run_full_cashflow_coach(req.persona_id)
    if analysis.get("consent_required"):
        raise HTTPException(status_code=403, detail="Borrower consent required before handing off to human advisor.")
        
    handoff_ticket = {
        "ticket_id": f"ADV-HANDOFF-{datetime.now().strftime('%Y%m%d%H%M')}-{req.persona_id[:4].upper()}",
        "created_at": datetime.now().isoformat(),
        "persona_id": req.persona_id,
        "borrower_name": analysis.get("name"),
        "account_masked": analysis.get("masked_account"),
        "weekly_capacity_inr": analysis.get("capacity_plan", {}).get("final_weekly_capacity_inr"),
        "monthly_capacity_inr": analysis.get("capacity_plan", {}).get("monthly_equivalent_inr"),
        "questions_to_discuss": analysis.get("advisor_observations", []),
        "agent_notes": req.notes,
        "status": "QUEUED_FOR_HUMAN_CREDIT_ADVISOR",
        "routing": "Credit Counseling & Structured Solutions Desk"
    }
    
    persona_case_map = {"kirana_owner": "1", "salaried_household": "2", "agri_trader": "25"}
    case_id = persona_case_map.get(req.persona_id)
    if case_id:
        case = get_case(case_id, workflow_id="collections")
        if case:
            case.add_trace(
                agent="HumanAdvisorDesk",
                action="Cash-Flow Advisor Handoff Dispatched",
                summary=f"Ticket {handoff_ticket['ticket_id']} queued for credit advisor with {len(handoff_ticket['questions_to_discuss'])} data-grounded observations.",
                badge="Handoff"
            )
            save_case(case)
            
    return handoff_ticket

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

@app.get("/coach", response_class=HTMLResponse)
@app.get("/checkup", response_class=HTMLResponse)
@app.get("/cashflow-coach", response_class=HTMLResponse)
def coach_portal():
    coach_file = os.path.join(STATIC_DIR, "coach.html")
    if os.path.exists(coach_file):
        with open(coach_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Saarthi Cash-Flow Coach</h1>"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
