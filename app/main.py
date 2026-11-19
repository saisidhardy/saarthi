import os
import csv
import json
import base64
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Response, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.models import CaseFile, DashboardMetrics
from app.database import init_db, save_case, get_case, get_all_cases, clear_all_cases
from agents.supervisor import run_supervisor_pipeline, run_supervisor_pipeline_stream
from agents.reporter import compute_dashboard_metrics

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    cases = get_all_cases()
    if not cases:
        load_sample_book()
    yield

app = FastAPI(title="Saarthi - Autonomous AI Collections Teammate", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models for request bodies
class MessageRequest(BaseModel):
    message: str

class EscalateRequest(BaseModel):
    reason: str
    assigned_human: Optional[str] = "Senior Operations Manager"

class TTSRequest(BaseModel):
    text: str
    language: Optional[str] = "Hindi"

class ConfigUpdateRequest(BaseModel):
    simulate: Optional[bool] = None
    demo_override_hours: Optional[bool] = None

# 1. Reset / Load Sample Book
@app.post("/api/load-sample-book")
def load_sample_book():
    clear_all_cases()
    csv_path = settings.SAMPLE_BOOK_PATH
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail="sample_book.csv not found")

    loaded_count = 0
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            case = CaseFile(
                id=str(row["id"]),
                borrower_name=row["borrower_name"],
                phone=row["phone"],
                language=row["language"],
                amount_due=float(row["amount_due"]),
                due_date=row["due_date"],
                dpd=int(row["dpd"]),
                loan_id=row["loan_id"],
                status="new",
                cost_inr=0.0,
                version=1
            )
            save_case(case)
            loaded_count += 1

    return {"status": "success", "loaded_accounts": loaded_count}

# 2. Get Cases
@app.get("/api/cases")
def list_cases():
    cases = get_all_cases()
    return cases

@app.get("/api/cases/{case_id}")
def get_single_case(case_id: str):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case

# 3. Run Pipeline (SSE or JSON)
@app.post("/api/cases/{case_id}/run")
def run_case_pipeline(case_id: str, stream: bool = Query(default=False)):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if stream:
        def event_stream():
            for updated_case in run_supervisor_pipeline_stream(case):
                yield f"data: {updated_case.model_dump_json()}\n\n"
        return StreamingResponse(event_stream(), media_type="text/event-stream")
    else:
        updated_case = run_supervisor_pipeline(case)
        return updated_case

# 4. In-call message / borrower response
@app.post("/api/cases/{case_id}/message")
def post_borrower_message(case_id: str, req: MessageRequest):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    updated_case = run_supervisor_pipeline(case, custom_borrower_reply=req.message)
    return updated_case

# 5. Simulate Payment
@app.post("/api/cases/{case_id}/simulate-payment")
def simulate_payment(case_id: str):
    case = get_case(case_id)
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

# 6. Escalate
@app.post("/api/cases/{case_id}/escalate")
def escalate_case(case_id: str, req: EscalateRequest):
    case = get_case(case_id)
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

# 7. Dashboard Metrics
@app.get("/api/dashboard")
def get_dashboard():
    return compute_dashboard_metrics()

# 8. Settings & Mode Toggle
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

# 9. Voice: STT & TTS
@app.post("/api/voice/stt")
def speech_to_text(request: Request):
    # If in simulate mode, return sample transcription
    if settings.SIMULATE or not settings.SARVAM_API_KEY:
        return {"transcript": "माझा पगार 5 तारखेला जमा होणार आहे, मी 5 तारखेला नक्की भरेन.", "language_code": "mr-IN"}
    
    # In live mode, call Sarvam Saaras
    try:
        from sarvamai import SarvamAI
        client = SarvamAI(api_subscription_key=settings.SARVAM_API_KEY)
        # Placeholder for multipart audio streaming
        return {"transcript": "Audio received (Live Sarvam)", "language_code": "hi-IN"}
    except Exception as e:
        return {"transcript": "Fallback: Audio transcribed", "language_code": "hi-IN", "error": str(e)}

@app.post("/api/voice/tts")
def text_to_speech(req: TTSRequest):
    # Returns audio synthesis instruction
    if settings.SIMULATE or not settings.SARVAM_API_KEY:
        return {
            "mode": "simulated",
            "text": req.text,
            "language": req.language,
            "browser_speech": True  # Instructs frontend Web Speech API or audio playback
        }
    
    try:
        from sarvamai import SarvamAI
        client = SarvamAI(api_subscription_key=settings.SARVAM_API_KEY)
        # Call Bulbul TTS
        return {
            "mode": "live",
            "text": req.text,
            "browser_speech": True
        }
    except Exception as e:
        return {"mode": "fallback", "text": req.text, "browser_speech": True}

# Static HTML Pages
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

# Mount static folder
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
