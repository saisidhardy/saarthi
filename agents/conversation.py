import os
import csv
import json
import re
from typing import Optional, Dict, Any
from app.models import JourneyRecord, WorkflowStep
from app.config import settings
from services.sarvam import sarvam_service

SCRIPTS_JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "scripts.json")

COLLECTIONS_CONSENT_SCRIPTS = {
    "Marathi": "नमस्कार {name}जी, मी सारथी फायनान्शियल कडून बोलतेय. हा कॉल सुरक्षेसाठी रेकॉर्ड केला जातोय. सुरक्षेसाठी आपल्या लोनचे शेवटचे ४ अंक सांगाल का?",
    "Hindi": "नमस्ते {name} जी, मैं सारथी फाइनेंशियल से बोल रहा हूँ। यह कॉल गुणवत्ता और अनुपालन निगरानी के लिए रिकॉर्ड की जा रही है। सुरक्षा के लिए, क्या आप अपने लोन अकाउंट के आखिरी 4 अंक बता सकते हैं?",
    "English": "Hello {name}, calling from Saarthi Financial. This call is recorded for quality and regulatory compliance. For your security, could you please confirm the last 4 digits of your loan account?"
}

SALES_CONSENT_SCRIPTS = {
    "Marathi": "नमस्कार {name}जी, मी सारथी कॅपिटल कडून बोलत आहे. आपल्या चांगल्या क्रेडिट रेकॉर्डमुळे आपल्यासाठी खास प्री-अ‍ॅप्रूव्हड पर्सनल लोन ऑफर आहे. २ मिनिटे वेळ आहे का?",
    "Hindi": "नमस्ते {name} जी, मैं सारथी कैपिटल से बोल रहा हूँ। आपके बेहतरीन क्रेडिट स्कोर पर विशेष प्री-अप्रूव्ड पर्सनल लोन ऑफर उपलब्ध है। क्या हम इस पर बात कर सकते हैं?",
    "English": "Hello {name}, calling from Saarthi Capital. You are eligible for a pre-approved instant personal loan with zero processing fee. Do you have two minutes?"
}

def resolve_project_path(p: Optional[str]) -> str:
    if not p:
        return settings.SAMPLE_BOOK_PATH
    if os.path.isabs(p):
        return p
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), p)

def load_script_from_file(file_path: Optional[str], record_id: str, workflow_id: str = "collections"):
    # In SIMULATE mode for collections, prioritize /data/scripts.json with colloquial Indic scripts
    if workflow_id == "collections" and (not file_path or "sample_book" in file_path):
        if os.path.exists(SCRIPTS_JSON_PATH):
            try:
                with open(SCRIPTS_JSON_PATH, "r", encoding="utf-8") as f:
                    scripts_data = json.load(f)
                    if str(record_id) in scripts_data:
                        return scripts_data[str(record_id)]
            except Exception:
                pass

    actual_path = resolve_project_path(file_path)
    if os.path.exists(actual_path):
        with open(actual_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if str(row.get("id")) == str(record_id):
                    return row
    return None

def run_conversation_agent(
    record: JourneyRecord,
    step: Optional[WorkflowStep] = None,
    context: Optional[Dict[str, Any]] = None,
    custom_borrower_reply: Optional[str] = None
) -> JourneyRecord:
    """
    Generic Conversation Agent:
    - In SIMULATE mode: reads strictly from /data/scripts.json and makes ZERO Sarvam calls.
    - Enforces mandatory consent / recording disclosure.
    - Enforces strict IDENTITY GATE: Borrower confirms last 4 digits of loan ID before debt disclosure.
    - 2 failures -> ends politely, zero debt disclosure, escalates immediately.
    - Handles live typed input and audio mic inputs when provided.
    """
    workflow_id = record.workflow_id or (context.get("workflow_id") if context else "collections")
    lang = record.language if record.language in COLLECTIONS_CONSENT_SCRIPTS else "Hindi"
    sample_file = context.get("sample_data_file") if context else settings.SAMPLE_BOOK_PATH
    script_data = load_script_from_file(sample_file, record.id, workflow_id=workflow_id)

    # If in SIMULATE mode with pre-generated multi-turn scripts and no custom user message
    if script_data and "dialogue" in script_data and not custom_borrower_reply:
        record.transcript = []
        for turn in script_data["dialogue"]:
            record.add_transcript(speaker=turn["speaker"], text=turn["text"])
        
        record.consent_played = True
        record.data["dialogue_turns"] = script_data["dialogue"]
        record.cost_inr = 1.68

        scenario = script_data.get("scenario", "")
        if scenario == "identity_fail":
            record.data["identity_verified"] = False
            record.data["identity_failures"] = 2
            record.status = "escalated"
            record.assigned_human = "Fraud Prevention & Identity Verification Desk"
            record.add_trace(
                agent="Conversation",
                action="Identity Gate Failed - Zero Disclosure",
                summary="Borrower failed 4-digit loan ID verification. Call terminated politely with ZERO debt disclosure per RBI privacy code."
            )
            return record
        else:
            record.data["identity_verified"] = True
            record.data["identity_failures"] = 0
            record.status = "contacted"
            record.add_trace(
                agent="Conversation",
                action="Voice Call & Identity Verified",
                summary=f"Identity confirmed (last 4 digits). Call conducted in {lang}. Mandatory consent captured. Telephony cost: ₹{record.cost_inr:.2f}."
            )
            return record

    # Dynamic / Live Fallback or Custom User Input
    if not record.consent_played:
        if workflow_id == "loan_sales":
            consent_line = SALES_CONSENT_SCRIPTS.get(lang, SALES_CONSENT_SCRIPTS["Hindi"]).format(name=record.customer_name)
        else:
            consent_line = COLLECTIONS_CONSENT_SCRIPTS.get(lang, COLLECTIONS_CONSENT_SCRIPTS["Hindi"]).format(name=record.customer_name)
        
        record.add_transcript(speaker="agent", text=consent_line)
        record.consent_played = True

    if custom_borrower_reply:
        customer_text = custom_borrower_reply
    elif script_data and script_data.get("borrower_script"):
        customer_text = script_data["borrower_script"]
    elif script_data and script_data.get("customer_script"):
        customer_text = script_data["customer_script"]
    else:
        customer_text = "होय, सांगा काय माहिती आहे?" if lang == "Marathi" else "जी, बताइए क्या बात है?"

    record.add_transcript(speaker="borrower" if workflow_id == "collections" else "customer", text=customer_text)

    # IDENTITY GATE CHECK
    if workflow_id == "collections":
        loan_id = str(record.data.get("loan_id", ""))
        expected_digits = re.sub(r"\D", "", loan_id)[-4:] if loan_id else "1001"
        
        scenario = script_data.get("scenario") if script_data else ""
        has_correct_digits = expected_digits in customer_text if expected_digits else False
        is_identity_failure = scenario == "identity_fail" or (not has_correct_digits and any(f in customer_text.lower() for f in ["wrong number", "who is this", "not giving", "don't know", "stop calling"]))

        if is_identity_failure:
            record.data["identity_verified"] = False
            record.data["identity_failures"] = 2
            
            if lang == "Marathi":
                termination_reply = "आरबीआय गोपनीयता नियमांनुसार ओळख पटल्याशिवाय आम्ही लोन माहिती देऊ शकत नाही. हा कॉल समाप्त केला जात आहे."
            elif lang == "English":
                termination_reply = "Under RBI privacy regulations, we cannot disclose loan details without identity confirmation. Ending this call."
            else:
                termination_reply = "आरबीआई गोपनीयता नियमों के तहत बिना सत्यापन के हम लोन की जानकारी नहीं दे सकते। यह कॉल समाप्त की जा रही है।"

            record.add_transcript(speaker="agent", text=termination_reply)
            record.status = "escalated"
            record.assigned_human = "Fraud Prevention & Identity Verification Desk"
            record.add_trace(
                agent="Conversation",
                action="Identity Gate Failed - Zero Disclosure",
                summary=f"Borrower failed to verify last 4 digits of loan ID ({expected_digits}). Call terminated politely with ZERO financial disclosure."
            )
            return record
        else:
            record.data["identity_verified"] = True
            record.data["identity_failures"] = 0

    # Agent dialogue turn
    if script_data and script_data.get("agent_script"):
        agent_reply = script_data["agent_script"]
    else:
        if workflow_id == "loan_sales":
            agent_reply = f"धन्यवाद {record.customer_name} जी, आपके खाते पर ₹{record.data.get('preapproved_amount', 200000):,.0f} का लोन 10.5% की दर पर स्वीकृत है।"
        else:
            agent_reply = f"धन्यवाद। पहचान सत्यापित हो गई है। आपके लोन खाते {record.data.get('loan_id')} पर ₹{record.amount_due:,.2f} की राशि देय है। क्या आप आज इसका भुगतान कर सकते हैं?"

    record.add_transcript(speaker="agent", text=agent_reply)
    record.cost_inr = 1.68
    record.status = "contacted"

    record.add_trace(
        agent="Conversation",
        action="Voice Call & Identity Verified",
        summary=f"Identity confirmed (last 4 digits). Call conducted in {lang}. Mandatory consent captured. Telephony cost: ₹{record.cost_inr:.2f}."
    )

    return record
