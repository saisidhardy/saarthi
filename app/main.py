import os
import csv
import json
import base64
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response, Query
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
    # Populate initial books if empty
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

class TTSRequest(BaseModel):
    text: str
    language: Optional[str] = "Hindi"

class ConfigUpdateRequest(BaseModel):
    simulate: Optional[bool] = None
    demo_override_hours: Optional[bool] = None

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
            # Ensure proper numeric typing in data dict
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

# 10. Voice STT / TTS
@app.post("/api/voice/stt")
def speech_to_text(request: Request):
    return {"transcript": "माझा पगार 5 तारखेला जमा होणार आहे, मी 5 तारखेला नक्की भरेन.", "language_code": "mr-IN"}

@app.post("/api/voice/tts")
def text_to_speech(req: TTSRequest):
    return {
        "mode": "simulated" if settings.SIMULATE else "live",
        "text": req.text,
        "language": req.language,
        "browser_speech": True
    }

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
