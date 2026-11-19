import pytest
import os
from app.config import settings
from app.models import JourneyRecord
from agents.decision import run_decision_agent
from agents.compliance import run_compliance_agent

def test_live_sarvam_decision_and_fallback():
    # Create test journey record with Marathi dialogue
    record = JourneyRecord(
        id="test_live_1",
        workflow_id="collections",
        customer_name="Aniket Deshmukh",
        phone="+919820112233",
        language="Marathi",
        status="contacted"
    )
    record.amount_due = 40000.0
    record.dpd = 3
    record.add_transcript("agent", "नमस्कार अनिकेतजी, 40000 रुपये देय आहेत.")
    record.add_transcript("borrower", "माझा पगार 5 तारखेला जमा होणार आहे, मी 5 तारखेला नक्की सर्व पैसे भरेन.")

    # Run with live Sarvam
    prev_sim = settings.SIMULATE
    try:
        settings.SIMULATE = False
        updated = run_decision_agent(record, context={"policy_file": "policies/collections_policy.txt", "workflow_id": "collections"})
        assert updated.intent == "ptp"
        assert updated.status == "ptp"
        assert updated.ptp_date is not None
        assert "Decision" in [t.agent for t in updated.trace]
    finally:
        settings.SIMULATE = prev_sim

def test_live_sarvam_compliance_audit():
    record = JourneyRecord(
        id="test_live_2",
        workflow_id="collections",
        customer_name="Aniket Deshmukh",
        phone="+919820112233",
        language="Marathi",
        status="ptp"
    )
    record.consent_played = True
    record.ptp_date = "2026-11-23"
    record.add_transcript("agent", "नमस्कार, हा कॉल रेकॉर्ड केला जात आहे. 40000 रुपये देय आहेत.")
    record.add_transcript("borrower", "होय, मी 23 तारखेला नक्की भरेन.")

    prev_sim = settings.SIMULATE
    try:
        settings.SIMULATE = False
        updated = run_compliance_agent(record, demo_override_hours=True)
        assert updated.audit_pass is True
        assert "PASSED" in updated.audit_reason
    finally:
        settings.SIMULATE = prev_sim

def test_automatic_fallback_on_invalid_key():
    record = JourneyRecord(
        id="test_fallback",
        workflow_id="collections",
        customer_name="Aniket Deshmukh",
        phone="+919820112233",
        language="Marathi",
        status="contacted"
    )
    record.amount_due = 40000.0
    record.dpd = 3
    record.add_transcript("agent", "नमस्ते")
    record.add_transcript("borrower", "अरे भाई, मैं तो 2 दिन पहले Google Pay से पैसे भर चुका हूँ!")

    prev_key = settings.SARVAM_API_KEY
    prev_sim = settings.SIMULATE
    try:
        settings.SIMULATE = False
        settings.SARVAM_API_KEY = "sk_invalid_bogus_key"
        # Should gracefully fall back to deterministic policy and detect dispute
        updated = run_decision_agent(record, context={"policy_file": "policies/collections_policy.txt", "workflow_id": "collections"})
        assert updated.intent == "dispute"
        assert updated.status == "escalated"
    finally:
        settings.SARVAM_API_KEY = prev_key
        settings.SIMULATE = prev_sim
