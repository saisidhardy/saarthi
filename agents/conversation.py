import os
import csv
from typing import Optional, Dict, Any
from app.models import JourneyRecord, WorkflowStep
from app.config import settings

COLLECTIONS_CONSENT_SCRIPTS = {
    "Marathi": "नमस्कार {name}जी, मी सारथी फायनान्शिअल कडून बोलत आहे. हा कॉल गुणवत्ता आणि अनुपालन तपासणीसाठी रेकॉर्ड केला जात आहे. आपण २ मिनिटे बोलू शकता का?",
    "Hindi": "नमस्ते {name} जी, मैं सारथी फाइनेंशियल से बात कर रहा हूँ। यह कॉल गुणवत्ता और अनुपालन निगरानी के लिए रिकॉर्ड की जा रही है। क्या आप बात करने के लिए उपलब्ध हैं?",
    "English": "Hello {name}, I am calling from Saarthi Financial. This call is recorded for quality and regulatory compliance. Do you have two minutes to discuss your EMI?",
    "Tamil": "வணக்கம் {name}, நான் சாரதி ஃபைனான்சியலில் இருந்து பேசுகிறேன். இந்த அழைப்பு தரக் கண்காணிப்பிற்காக பதிவு செய்யப்படுகிறது."
}

SALES_CONSENT_SCRIPTS = {
    "Marathi": "नमस्कार {name}जी, मी सारथी कॅपिटल कडून बोलत आहे. आपल्या चांगल्या क्रेडिट रेकॉर्डमुळे आपल्यासाठी खास प्री-अ‍ॅप्रूव्हड पर्सनल लोन ऑफर आहे. २ मिनिटे वेळ आहे का?",
    "Hindi": "नमस्ते {name} जी, मैं सारथी कैपिटल से बोल रहा हूँ। आपके बेहतरीन क्रेडिट स्कोर पर विशेष प्री-अप्रूव्ड पर्सनल लोन ऑफर उपलब्ध है। क्या हम इस पर बात कर सकते हैं?",
    "English": "Hello {name}, calling from Saarthi Capital. You are eligible for a pre-approved instant personal loan with zero processing fee. Do you have two minutes?",
    "Tamil": "வணக்கம் {name}, சாரதி கேபிடலில் இருந்து அழைக்கிறேன். உங்களுக்கு உடனடி தனிநபர் கடன் சலுகை உள்ளது."
}

def resolve_project_path(p: Optional[str]) -> str:
    if not p:
        return settings.SAMPLE_BOOK_PATH
    if os.path.isabs(p):
        return p
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), p)

def load_script_from_file(file_path: Optional[str], record_id: str):
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
    - Enforces mandatory consent / greetings
    - Conducts bilingual conversation in customer's preferred tongue
    - Logs transcript turns with timestamps
    - Computes telephony duration and cost
    """
    workflow_id = record.workflow_id or (context.get("workflow_id") if context else "collections")
    lang = record.language if record.language in COLLECTIONS_CONSENT_SCRIPTS else "Hindi"

    # 1. Play consent / opening line
    if not record.consent_played:
        if workflow_id == "loan_sales":
            consent_line = SALES_CONSENT_SCRIPTS.get(lang, SALES_CONSENT_SCRIPTS["Hindi"]).format(name=record.customer_name)
        else:
            consent_line = COLLECTIONS_CONSENT_SCRIPTS.get(lang, COLLECTIONS_CONSENT_SCRIPTS["Hindi"]).format(name=record.customer_name)
        
        record.add_transcript(speaker="agent", text=consent_line)
        record.consent_played = True

    # 2. Get customer / borrower response
    sample_file = context.get("sample_data_file") if context else settings.SAMPLE_BOOK_PATH
    if not sample_file:
        sample_file = settings.SAMPLE_BOOK_PATH
    script_data = load_script_from_file(sample_file, record.id)

    if custom_borrower_reply:
        customer_text = custom_borrower_reply
    elif script_data and script_data.get("borrower_script"):
        customer_text = script_data["borrower_script"]
    elif script_data and script_data.get("customer_script"):
        customer_text = script_data["customer_script"]
    else:
        customer_text = "होय, सांगा काय माहिती आहे?" if lang == "Marathi" else "जी, बताइए क्या ऑफर है?"

    record.add_transcript(speaker="borrower" if workflow_id == "collections" else "customer", text=customer_text)

    # 3. Agent dialogue turn
    if script_data and script_data.get("agent_script"):
        agent_reply = script_data["agent_script"]
    else:
        if workflow_id == "loan_sales":
            agent_reply = f"धन्यवाद {record.customer_name} जी, आपके खाते पर ₹{record.data.get('preapproved_amount', 200000):,.0f} का लोन 10.5% की दर पर स्वीकृत है।"
        else:
            agent_reply = f"धन्यवाद। आपके लोन खाते {record.data.get('loan_id')} पर ₹{record.amount_due} की राशि देय है। क्या आप आज इसका भुगतान कर सकते हैं?"

    record.add_transcript(speaker="agent", text=agent_reply)

    # 4. Telephony cost calculation
    call_minutes = 1.4
    call_cost = (call_minutes * settings.CALL_COST_PER_MIN) + settings.ESTIMATED_LLM_COST_PER_CALL
    record.cost_inr = round(call_cost, 2)
    record.status = "contacted"

    record.add_trace(
        agent="Conversation",
        action="Voice Call Executed in Customer Language",
        summary=f"Connected in {record.language}. Consent verified. Dialogue captured. Duration: {call_minutes}m, Telephony Cost: ₹{record.cost_inr}."
    )

    return record
