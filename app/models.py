from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime, timezone

class TranscriptItem(BaseModel):
    speaker: str  # 'agent' | 'borrower' | 'system'
    text: str
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class TraceItem(BaseModel):
    agent: str  # 'Supervisor' | 'Intake' | 'Conversation' | 'Negotiation' | 'Action' | 'Compliance' | 'Reporter'
    action: str
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    summary: str

class CaseFile(BaseModel):
    id: str
    borrower_name: str
    phone: str
    language: str  # 'Hindi' | 'Marathi' | 'English' | 'Tamil'
    amount_due: float
    due_date: str
    dpd: int
    loan_id: str
    risk_note: Optional[str] = ""
    tone_hint: Optional[str] = ""
    best_call_window: Optional[str] = "10:00 - 12:00 IST"
    consent_played: bool = False
    transcript: List[TranscriptItem] = Field(default_factory=list)
    intent: Optional[Literal["ptp", "hardship", "dispute", "avoidance", "none"]] = "none"
    sentiment: Optional[str] = "neutral"
    offer_made: Optional[str] = None
    ptp_date: Optional[str] = None
    confidence: float = 0.0
    payment_link: Optional[str] = None
    payment_status: Literal["none", "sent", "paid"] = "none"
    audit_pass: Optional[bool] = None
    audit_reason: Optional[str] = None
    status: Literal["new", "contacted", "ptp", "paid", "escalated"] = "new"
    assigned_human: Optional[str] = None
    cost_inr: float = 0.0
    version: int = 1
    trace: List[TraceItem] = Field(default_factory=list)

    def add_trace(self, agent: str, action: str, summary: str):
        self.trace.append(TraceItem(
            agent=agent,
            action=action,
            ts=datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
            summary=summary
        ))
        self.version += 1

    def add_transcript(self, speaker: str, text: str):
        self.transcript.append(TranscriptItem(
            speaker=speaker,
            text=text,
            ts=datetime.now(timezone.utc).strftime("%H:%M:%S")
        ))
        self.version += 1

class DashboardMetrics(BaseModel):
    total_accounts: int
    contacted: int
    ptps: int
    paid: int
    escalated: int
    ptp_conversion_pct: float
    recovery_pct: float
    total_cost_inr: float
    our_cost_per_contact: float
    industry_call_centre_cost: float = 52.00
    industry_field_visit_cost: float = 250.00
    language_breakdown: dict
