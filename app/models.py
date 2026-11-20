from typing import List, Optional, Literal, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, model_validator, computed_field

class TranscriptItem(BaseModel):
    speaker: str  # 'agent' | 'borrower' | 'system' | 'customer'
    text: str
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class TraceItem(BaseModel):
    agent: str  # Agent name or 'Supervisor'
    action: str
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    summary: str
    badge: Optional[str] = None  # e.g. 'Event Trigger', 'Policy Firewall', 'Review/Critique', 'Human-in-the-loop'

class LLMProposal(BaseModel):
    intent: str = "ptp"  # 'ptp' | 'part_payment' | 'hardship' | 'dispute' | 'avoidance' | 'adversarial'
    offered_amount: Optional[float] = None
    date_phrase: Optional[str] = None
    waiver_requested: bool = False
    requested_days: Optional[int] = None
    sentiment: str = "neutral"
    confidence: float = 0.95
    raw_response: Optional[str] = None

class PolicyDecision(BaseModel):
    status: str  # 'APPROVED' | 'CLAMPED' | 'BLOCKED' | 'ESCALATED' | 'SENSITIVE_PAUSE'
    rule_id: str  # e.g. 'POLICY-WAIVER-NO01', 'POLICY-PTP-MAX01', 'FAIR-PRAC-SENS01', 'POLICY-PREV-FEE01', 'POLICY-MICRO-SPLIT01'
    yaml_line: int  # Line number in collections_rules.yaml
    yaml_file: str = "policies/collections_rules.yaml"
    effective_amount: float
    effective_date: Optional[str] = None
    reason: str
    needs_human: bool = False
    assigned_human: Optional[str] = None
    do_not_contact_until: Optional[str] = None
    action_permitted: bool = False
    llm_proposed_summary: str
    engine_decision_summary: str
    micro_schedule: Optional[List[Dict[str, Any]]] = None
    bounce_fee_saved_inr: float = 0.0
    hospicash_claim: Optional[Dict[str, Any]] = None
    root_cause: Optional[str] = None
    downstream_action: Optional[Dict[str, Any]] = None
    instant_recovered_inr: float = 0.0
    locked_mandate_inr: float = 0.0
    why_recovery_increased: Optional[Dict[str, Any]] = None

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
            for k in [
                "amount_due", "due_date", "dpd", "loan_id", "risk_note", "tone_hint", 
                "best_call_window", "consent_played", "ai_disclosure_played", 
                "recording_disclosure_played", "human_opt_out_offered", "third_party_contact",
                "do_not_contact_until", "attempts_count", "call_start", "call_end",
                "preferred_contact_window", "intent", "sentiment", "offer_made", 
                "ptp_date", "confidence", "payment_link", "payment_status", 
                "audit_pass", "audit_reason", "trigger_type", "micro_schedule",
                "has_hospicash_rider", "policy_number", "hospicash_claim",
                "bounce_fee_saved_inr", "root_cause", "downstream_action",
                "pre_due_balance_inr", "instant_recovered_inr", "locked_mandate_inr",
                "why_recovery_increased", "repayment_rail", "cibil_protected",
                "qr_sweep_active", "qr_sweep_pct"
            ]:
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

    @computed_field
    @property
    def dpd(self) -> int:
        return int(self.data.get("dpd", 0))

    @dpd.setter
    def dpd(self, val: int):
        self.data["dpd"] = int(val)

    @computed_field
    @property
    def loan_id(self) -> str:
        return str(self.data.get("loan_id", ""))

    @loan_id.setter
    def loan_id(self, val: str):
        self.data["loan_id"] = val

    @computed_field
    @property
    def risk_note(self) -> str:
        return str(self.data.get("risk_note", ""))

    @risk_note.setter
    def risk_note(self, val: str):
        self.data["risk_note"] = val

    @computed_field
    @property
    def tone_hint(self) -> str:
        return str(self.data.get("tone_hint", ""))

    @tone_hint.setter
    def tone_hint(self, val: str):
        self.data["tone_hint"] = val

    @computed_field
    @property
    def best_call_window(self) -> str:
        return str(self.data.get("best_call_window", "10:00 - 12:00 IST"))

    @best_call_window.setter
    def best_call_window(self, val: str):
        self.data["best_call_window"] = val

    @computed_field
    @property
    def consent_played(self) -> bool:
        return bool(self.data.get("consent_played", False))

    @consent_played.setter
    def consent_played(self, val: bool):
        self.data["consent_played"] = bool(val)

    @computed_field
    @property
    def intent(self) -> str:
        return str(self.data.get("intent", "none"))

    @intent.setter
    def intent(self, val: str):
        self.data["intent"] = val

    @computed_field
    @property
    def sentiment(self) -> str:
        return str(self.data.get("sentiment", "neutral"))

    @sentiment.setter
    def sentiment(self, val: str):
        self.data["sentiment"] = val

    @computed_field
    @property
    def offer_made(self) -> Optional[str]:
        return self.data.get("offer_made")

    @offer_made.setter
    def offer_made(self, val: Optional[str]):
        self.data["offer_made"] = val

    @computed_field
    @property
    def ptp_date(self) -> Optional[str]:
        return self.data.get("ptp_date")

    @ptp_date.setter
    def ptp_date(self, val: Optional[str]):
        self.data["ptp_date"] = val

    @computed_field
    @property
    def confidence(self) -> float:
        return float(self.data.get("confidence", 0.0))

    @confidence.setter
    def confidence(self, val: float):
        self.data["confidence"] = float(val)

    @computed_field
    @property
    def payment_link(self) -> Optional[str]:
        return self.data.get("payment_link")

    @payment_link.setter
    def payment_link(self, val: Optional[str]):
        self.data["payment_link"] = val

    @computed_field
    @property
    def payment_status(self) -> str:
        return str(self.data.get("payment_status", "none"))

    @payment_status.setter
    def payment_status(self, val: str):
        self.data["payment_status"] = val

    @computed_field
    @property
    def audit_pass(self) -> Optional[bool]:
        return self.data.get("audit_pass")

    @audit_pass.setter
    def audit_pass(self, val: Optional[bool]):
        self.data["audit_pass"] = val

    @computed_field
    @property
    def audit_reason(self) -> Optional[str]:
        return self.data.get("audit_reason")

    @audit_reason.setter
    def audit_reason(self, val: Optional[str]):
        self.data["audit_reason"] = val

    @computed_field
    @property
    def ai_disclosure_played(self) -> bool:
        return bool(self.data.get("ai_disclosure_played", False))

    @ai_disclosure_played.setter
    def ai_disclosure_played(self, val: bool):
        self.data["ai_disclosure_played"] = bool(val)

    @computed_field
    @property
    def recording_disclosure_played(self) -> bool:
        return bool(self.data.get("recording_disclosure_played", False))

    @recording_disclosure_played.setter
    def recording_disclosure_played(self, val: bool):
        self.data["recording_disclosure_played"] = bool(val)

    @computed_field
    @property
    def human_opt_out_offered(self) -> bool:
        return bool(self.data.get("human_opt_out_offered", False))

    @human_opt_out_offered.setter
    def human_opt_out_offered(self, val: bool):
        self.data["human_opt_out_offered"] = bool(val)

    @computed_field
    @property
    def third_party_contact(self) -> bool:
        return bool(self.data.get("third_party_contact", False))

    @third_party_contact.setter
    def third_party_contact(self, val: bool):
        self.data["third_party_contact"] = bool(val)

    @computed_field
    @property
    def do_not_contact_until(self) -> Optional[str]:
        return self.data.get("do_not_contact_until")

    @do_not_contact_until.setter
    def do_not_contact_until(self, val: Optional[str]):
        self.data["do_not_contact_until"] = val

    @computed_field
    @property
    def trigger_type(self) -> str:
        return str(self.data.get("trigger_type", "POST_BOUNCE"))

    @trigger_type.setter
    def trigger_type(self, val: str):
        self.data["trigger_type"] = val

    @computed_field
    @property
    def micro_schedule(self) -> Optional[List[Dict[str, Any]]]:
        return self.data.get("micro_schedule")

    @micro_schedule.setter
    def micro_schedule(self, val: Optional[List[Dict[str, Any]]]):
        self.data["micro_schedule"] = val

    @computed_field
    @property
    def has_hospicash_rider(self) -> bool:
        return bool(self.data.get("has_hospicash_rider", False))

    @has_hospicash_rider.setter
    def has_hospicash_rider(self, val: bool):
        self.data["has_hospicash_rider"] = bool(val)

    @computed_field
    @property
    def policy_number(self) -> Optional[str]:
        return self.data.get("policy_number")

    @policy_number.setter
    def policy_number(self, val: Optional[str]):
        self.data["policy_number"] = val

    @computed_field
    @property
    def hospicash_claim(self) -> Optional[Dict[str, Any]]:
        return self.data.get("hospicash_claim")

    @hospicash_claim.setter
    def hospicash_claim(self, val: Optional[Dict[str, Any]]):
        self.data["hospicash_claim"] = val

    @computed_field
    @property
    def bounce_fee_saved_inr(self) -> float:
        return float(self.data.get("bounce_fee_saved_inr", 0.0))

    @bounce_fee_saved_inr.setter
    def bounce_fee_saved_inr(self, val: float):
        self.data["bounce_fee_saved_inr"] = float(val)

    @computed_field
    @property
    def root_cause(self) -> Optional[str]:
        return self.data.get("root_cause")

    @root_cause.setter
    def root_cause(self, val: Optional[str]):
        self.data["root_cause"] = val

    @computed_field
    @property
    def downstream_action(self) -> Optional[Dict[str, Any]]:
        return self.data.get("downstream_action")

    @downstream_action.setter
    def downstream_action(self, val: Optional[Dict[str, Any]]):
        self.data["downstream_action"] = val

    @computed_field
    @property
    def instant_recovered_inr(self) -> float:
        return float(self.data.get("instant_recovered_inr", 0.0))

    @instant_recovered_inr.setter
    def instant_recovered_inr(self, val: float):
        self.data["instant_recovered_inr"] = float(val)

    @computed_field
    @property
    def locked_mandate_inr(self) -> float:
        return float(self.data.get("locked_mandate_inr", 0.0))

    @locked_mandate_inr.setter
    def locked_mandate_inr(self, val: float):
        self.data["locked_mandate_inr"] = float(val)

    @computed_field
    @property
    def why_recovery_increased(self) -> Optional[Dict[str, Any]]:
        return self.data.get("why_recovery_increased")

    @why_recovery_increased.setter
    def why_recovery_increased(self, val: Optional[Dict[str, Any]]):
        self.data["why_recovery_increased"] = val

    @computed_field
    @property
    def repayment_rail(self) -> Optional[str]:
        return self.data.get("repayment_rail")

    @repayment_rail.setter
    def repayment_rail(self, val: Optional[str]):
        self.data["repayment_rail"] = val

    @computed_field
    @property
    def cibil_protected(self) -> bool:
        return bool(self.data.get("cibil_protected", False))

    @cibil_protected.setter
    def cibil_protected(self, val: bool):
        self.data["cibil_protected"] = bool(val)

    @computed_field
    @property
    def masked_phone(self) -> str:
        clean = self.phone.replace(" ", "").replace("-", "")
        if len(clean) >= 4:
            return "XXXXXX" + clean[-4:]
        return "XXXXXX"

    def add_trace(self, agent: str, action: str, summary: str, badge: Optional[str] = None):
        self.trace.append(TraceItem(
            agent=agent,
            action=action,
            ts=datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
            summary=summary,
            badge=badge
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
    recovery_lift_pct: float = 61.2
    baseline_recovery_pct: float = 34.0
    portfolio_recovery_rate_pct: float = 61.8
    total_bounce_fees_saved_inr: float = 0.0
    npa_loans_rescued_count: int = 0
    cash_recovered_today_inr: float = 0.0
    future_cash_locked_inr: float = 0.0
    npa_and_fees_prevented_inr: float = 0.0
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
