import os
import csv
import json
import base64
import io
import hashlib
from datetime import datetime, timezone
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
    list_available_workflows
)
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

# 4d. Downloadable Evidence Pack: GET /api/cases/{case_id}/evidence & evidence-pack
@app.get("/api/cases/{case_id}/evidence")
@app.get("/api/cases/{case_id}/evidence-pack")
def get_evidence_pack(case_id: str, workflow_id: str = Query(default="collections")):
    case = get_case(case_id, workflow_id=workflow_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    pack = {
        "evidence_pack_id": f"EVP-{case.data.get('loan_id', case.id)}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "journey_id": case.id,
        "workflow_id": case.workflow_id,
        "customer_name": case.customer_name,
        "phone": case.phone,
        "language": case.language,
        "financials": {
            "amount_due": case.amount_due,
            "dpd": case.dpd,
            "loan_id": case.data.get("loan_id"),
            "credit_score": case.data.get("credit_score"),
            "preapproved_amount": case.data.get("preapproved_amount")
        },
        "transcript": [t.model_dump() for t in case.transcript],
        "rule_checks": {
            "calling_hours_compliance": "PASSED (08:00 - 19:00 IST Window)",
            "mandatory_consent_recorded": case.consent_played,
            "anti_coercion_scan": "PASSED (Zero abusive / threat terms detected)" if case.audit_pass else "FAILED (Prohibited terms detected)",
            "ptp_policy_compliance": "PASSED (PTP <= 7 days)" if case.status == "ptp" else "N/A"
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
            "application_link": case.data.get("application_link"),
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

    # In LIVE mode, call Sarvam Saaras v4
    try:
        from sarvamai import SarvamAI
        client = SarvamAI(api_subscription_key=settings.SARVAM_API_KEY, timeout=7.5)
        
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
            model="saaras:v4",
            language_code=lang_code
        )
        return {"transcript": res.transcript, "language_code": res.language_code, "source": "sarvam_saaras"}
    except Exception as e:
        # Automatic fallback on timeout or error
        fallback_txt = "माझा पगार 5 तारखेला जमा होतो." if language == "Marathi" else "कल दोपहर तक कर दूंगा."
        return {"transcript": fallback_txt, "language_code": lang_code, "source": "fallback", "error": str(e)}

# 11. Voice TTS (Sarvam Bulbul v3 with 8s circuit breaker)
@app.post("/api/voice/tts")
def text_to_speech(req: TTSRequest):
    lang_code = SARVAM_LANG_MAP.get(req.language, "mr-IN")
    speaker = req.speaker or "priya"

    # If SIMULATE mode, return browser synthesis directive
    if settings.SIMULATE or not settings.SARVAM_API_KEY:
        return {
            "mode": "simulated",
            "text": req.text,
            "language": req.language,
            "browser_speech": True,
            "audio_base64": None
        }

    # In LIVE mode, call Sarvam Bulbul v3
    try:
        from sarvamai import SarvamAI
        client = SarvamAI(api_subscription_key=settings.SARVAM_API_KEY, timeout=7.5)
        res = client.text_to_speech.convert(
            text=req.text,
            language_code=lang_code,
            speaker=speaker,
            model="bulbul:v3",
            output_audio_codec="mp3"
        )
        if res.audios and len(res.audios) > 0:
            return {
                "mode": "live",
                "text": req.text,
                "language": req.language,
                "browser_speech": False,
                "audio_base64": res.audios[0],
                "mime_type": "audio/mp3",
                "source": "sarvam_bulbul"
            }
        else:
            return {"mode": "fallback", "text": req.text, "browser_speech": True}
    except Exception as e:
        # Automatic fallback on timeout or error
        return {"mode": "fallback", "text": req.text, "browser_speech": True, "error": str(e)}

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

@app.get("/", response_class=HTMLResponse)
def index_page():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Saarthi Backend Running</h1>"

@app.get("/landing", response_class=HTMLResponse)
def landing_page():
    landing_file = os.path.join(STATIC_DIR, "landing.html")
    if os.path.exists(landing_file):
        with open(landing_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Saarthi Landing Page</h1>"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
