from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator

class TranscriptItem(BaseModel):
    speaker: str  # 'agent' | 'borrower' | 'system' | 'customer'
    text: str
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class TraceItem(BaseModel):
    agent: str  # Agent name or 'Supervisor'
    action: str
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    summary: str

class JourneyRecord(BaseModel):
    id: str
    workflow_id: str = "collections"
    customer_name: str = ""
    phone: str
    language: str = "Hindi"
    status: str = "new"  # 'new' | 'contacted' | 'ptp' | 'paid' | 'escalated' | 'completed' | 'qualified'
    stage: str = "new"
    assigned_human: Optional[str] = None
    cost_inr: float = 0.0
    version: int = 1
    transcript: List[TranscriptItem] = Field(default_factory=list)
    trace: List[TraceItem] = Field(default_factory=list)
    data: Dict[str, Any] = Field(default_factory=dict)  # Generic shared memory dict

    @model_validator(mode="before")
    @classmethod
    def populate_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            # Map borrower_name to customer_name if provided
            if "borrower_name" in values and not values.get("customer_name"):
                values["customer_name"] = values["borrower_name"]
            
            # Populate data dict from incoming collections fields if not already in data
            data = values.get("data", {})
            for k in ["amount_due", "due_date", "dpd", "loan_id", "risk_note", "tone_hint", "best_call_window", "consent_played", "intent", "sentiment", "offer_made", "ptp_date", "confidence", "payment_link", "payment_status", "audit_pass", "audit_reason"]:
                if k in values:
                    data[k] = values[k]
            values["data"] = data
        return values

    # Backward compatibility / convenience properties for Collections
    @property
    def borrower_name(self) -> str:
        return self.customer_name

    @borrower_name.setter
    def borrower_name(self, val: str):
        self.customer_name = val

    @property
    def amount_due(self) -> float:
        return float(self.data.get("amount_due", 0.0))

    @amount_due.setter
    def amount_due(self, val: float):
        self.data["amount_due"] = float(val)

    @property
    def due_date(self) -> str:
        return str(self.data.get("due_date", ""))

    @due_date.setter
    def due_date(self, val: str):
        self.data["due_date"] = val

    @property
    def dpd(self) -> int:
        return int(self.data.get("dpd", 0))

    @dpd.setter
    def dpd(self, val: int):
        self.data["dpd"] = int(val)

    @property
    def loan_id(self) -> str:
        return str(self.data.get("loan_id", ""))

    @loan_id.setter
    def loan_id(self, val: str):
        self.data["loan_id"] = val

    @property
    def risk_note(self) -> str:
        return str(self.data.get("risk_note", ""))

    @risk_note.setter
    def risk_note(self, val: str):
        self.data["risk_note"] = val

    @property
    def tone_hint(self) -> str:
        return str(self.data.get("tone_hint", ""))

    @tone_hint.setter
    def tone_hint(self, val: str):
        self.data["tone_hint"] = val

    @property
    def best_call_window(self) -> str:
        return str(self.data.get("best_call_window", "10:00 - 12:00 IST"))

    @best_call_window.setter
    def best_call_window(self, val: str):
        self.data["best_call_window"] = val

    @property
    def consent_played(self) -> bool:
        return bool(self.data.get("consent_played", False))

    @consent_played.setter
    def consent_played(self, val: bool):
        self.data["consent_played"] = bool(val)

    @property
    def intent(self) -> str:
        return str(self.data.get("intent", "none"))

    @intent.setter
    def intent(self, val: str):
        self.data["intent"] = val

    @property
    def sentiment(self) -> str:
        return str(self.data.get("sentiment", "neutral"))

    @sentiment.setter
    def sentiment(self, val: str):
        self.data["sentiment"] = val

    @property
    def offer_made(self) -> Optional[str]:
        return self.data.get("offer_made")

    @offer_made.setter
    def offer_made(self, val: Optional[str]):
        self.data["offer_made"] = val

    @property
    def ptp_date(self) -> Optional[str]:
        return self.data.get("ptp_date")

    @ptp_date.setter
    def ptp_date(self, val: Optional[str]):
        self.data["ptp_date"] = val

    @property
    def confidence(self) -> float:
        return float(self.data.get("confidence", 0.0))

    @confidence.setter
    def confidence(self, val: float):
        self.data["confidence"] = float(val)

    @property
    def payment_link(self) -> Optional[str]:
        return self.data.get("payment_link")

    @payment_link.setter
    def payment_link(self, val: Optional[str]):
        self.data["payment_link"] = val

    @property
    def payment_status(self) -> str:
        return str(self.data.get("payment_status", "none"))

    @payment_status.setter
    def payment_status(self, val: str):
        self.data["payment_status"] = val

    @property
    def audit_pass(self) -> Optional[bool]:
        return self.data.get("audit_pass")

    @audit_pass.setter
    def audit_pass(self, val: Optional[bool]):
        self.data["audit_pass"] = val

    @property
    def audit_reason(self) -> Optional[str]:
        return self.data.get("audit_reason")

    @audit_reason.setter
    def audit_reason(self, val: Optional[str]):
        self.data["audit_reason"] = val

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

# Alias for CaseFile backward compatibility
CaseFile = JourneyRecord

class WorkflowStep(BaseModel):
    id: str
    name: str
    agent: str
    retry_limit: int = 3
    on_failure: str = "escalate"
    condition: Optional[str] = None
    input_fields: List[str] = Field(default_factory=list)
    output_fields: List[str] = Field(default_factory=list)

class EscalationRule(BaseModel):
    condition: str
    target_desk: str
    reason: str

class WorkflowDefinition(BaseModel):
    id: str
    name: str
    goal: str
    success_metric: str
    policy_file: Optional[str] = None
    sample_data_file: Optional[str] = None
    human_escalation_rules: List[EscalationRule] = Field(default_factory=list)
    steps: List[WorkflowStep] = Field(default_factory=list)

class EngineMetrics(BaseModel):
    workflow_id: str
    workflow_name: str
    journeys_started: int
    journeys_completed_autonomously: int
    human_touch_count: int
    human_touch_rate_pct: float
    total_cost_inr: float
    cost_per_completed_journey: float
    workflow_metric_name: str
    workflow_metric_value: float
    industry_call_centre_cost: float = 52.00
    industry_field_visit_cost: float = 250.00
    details: Dict[str, Any] = Field(default_factory=dict)

    # Convenience properties for backward compatibility
    @property
    def contacted(self) -> int:
        return self.journeys_started

    @property
    def ptps(self) -> int:
        return int(self.details.get("ptps", 0))

    @property
    def paid(self) -> int:
        return int(self.details.get("paid", 0))

    @property
    def escalated(self) -> int:
        return self.human_touch_count

    @property
    def our_cost_per_contact(self) -> float:
        return float(self.details.get("our_cost_per_contact", self.cost_per_completed_journey))

    @property
    def ptp_conversion_pct(self) -> float:
        return self.workflow_metric_value

    @property
    def recovery_pct(self) -> float:
        return float(self.details.get("recovery_pct", self.workflow_metric_value))

# Alias for backward compatibility
DashboardMetrics = EngineMetrics
