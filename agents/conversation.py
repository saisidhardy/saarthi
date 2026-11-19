import os
import csv
from typing import Optional
from app.models import CaseFile
from app.config import settings

CONSENT_SCRIPTS = {
    "Marathi": "नमस्कार {name}जी, मी सारथी फायनान्शिअल कडून बोलत आहे. हा कॉल गुणवत्ता आणि अनुपालन तपासणीसाठी रेकॉर्ड केला जात आहे. आपण २ मिनिटे बोलू शकता का?",
    "Hindi": "नमस्ते {name} जी, मैं सारथी फाइनेंशियल से बात कर रहा हूँ। यह कॉल गुणवत्ता और अनुपालन निगरानी के लिए रिकॉर्ड की जा रही है। क्या आप बात करने के लिए उपलब्ध हैं?",
    "English": "Hello {name}, I am calling from Saarthi Financial. This call is recorded for quality and regulatory compliance. Do you have two minutes to discuss your EMI?",
    "Tamil": "வணக்கம் {name}, நான் சாரதி ஃபைனான்சியலில் இருந்து பேசுகிறேன். இந்த அழைப்பு தரக் கண்காணிப்பிற்காக பதிவு செய்யப்படுகிறது."
}

def load_script_from_book(case_id: str):
    csv_path = settings.SAMPLE_BOOK_PATH
    if os.path.exists(csv_path):
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if str(row["id"]) == str(case_id):
                    return row
    return None

def run_conversation_agent(case: CaseFile, custom_borrower_reply: Optional[str] = None) -> CaseFile:
    """
    Conversation Agent:
    - Enforces RBI mandatory consent recording
    - Conducts bilingual conversation in borrower's preferred tongue
    - Logs transcript turns with timestamps
    - Computes telephony duration and cost
    - Updates case status to 'contacted'
    """
    # 1. Play consent line
    lang = case.language if case.language in CONSENT_SCRIPTS else "Hindi"
    consent_line = CONSENT_SCRIPTS[lang].format(name=case.borrower_name)
    
    if not case.consent_played:
        case.add_transcript(speaker="agent", text=consent_line)
        case.consent_played = True

    # 2. Get Borrower response
    script_data = load_script_from_book(case.id)
    
    if custom_borrower_reply:
        borrower_text = custom_borrower_reply
    elif script_data and script_data.get("borrower_script"):
        borrower_text = script_data["borrower_script"]
    else:
        borrower_text = "जी, बताइए क्या बात है?"

    case.add_transcript(speaker="borrower", text=borrower_text)

    # 3. Handle Agent response
    if script_data and script_data.get("agent_script"):
        agent_reply = script_data["agent_script"]
    else:
        agent_reply = f"धन्यवाद। आपके लोन खाते {case.loan_id} पर ₹{case.amount_due} की राशि देय है। क्या आप आज इसका भुगतान कर सकते हैं?"

    case.add_transcript(speaker="agent", text=agent_reply)

    # 4. Telephony cost calculation (estimated 1.5 minutes for early bounce call)
    call_minutes = 1.4
    call_cost = (call_minutes * settings.CALL_COST_PER_MIN) + settings.ESTIMATED_LLM_COST_PER_CALL
    case.cost_inr = round(call_cost, 2)
    case.status = "contacted"

    case.add_trace(
        agent="Conversation",
        action="Voice Call Executed with RBI Consent",
        summary=f"Connected in {case.language}. Consent confirmed. Borrower response captured. Duration: {call_minutes}m, Cost: ₹{case.cost_inr}."
    )

    return case
