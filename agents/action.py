import hashlib
from typing import Optional
from app.models import CaseFile

WHATSAPP_TEMPLATES = {
    "Marathi": """प्रिय {name}जी,
सारथी फायनान्शिअल सोबत बोलल्याबद्दल धन्यवाद. आपल्या विनंतीनुसार लोन खाते {loan_id} च्या ₹{amount} देय रकमेसाठी PTP तारीख {ptp_date} नोंदवली आहे.

तात्काळ किंवा देय तारखेपूर्वी भरणा करण्यासाठी खालील अधिकृत UPI लिंक वापरा:
{link}

(टीप: हे केवळ प्रात्यक्षिक डेटा आहे - Demo lender sample data)""",

    "Hindi": """प्रिय {name} जी,
सारथी फाइनेंशियल से बात करने के लिए धन्यवाद। आपके लोन खाते {loan_id} के ₹{amount} बकाया के लिए PTP तारीख {ptp_date} दर्ज कर ली गई है।

भुगतान करने के लिए इस सुरक्षित UPI लिंक का उपयोग करें:
{link}

(नोट: यह केवल डेमो डेटा है - Demo lender sample data)""",

    "English": """Dear {name},
Thank you for speaking with Saarthi Financial. As agreed, your Promise-to-Pay (PTP) for loan account {loan_id} of ₹{amount} is scheduled for {ptp_date}.

Use this secure UPI link to complete your payment:
{link}

(Note: Demo lender - sample data only. No real money moves.)""",

    "Tamil": """அன்புள்ள {name},
சாரதி ஃபைனான்சியலில் பேசியதற்கு நன்றி. உங்கள் கடன் கணக்கு {loan_id}-க்கான ₹{amount} தொகைக்கான PTP தேதி {ptp_date} பதிவு செய்யப்பட்டுள்ளது.

UPI இணைப்பு:
{link}

(குறிப்பு: டெமோ கடன் வழங்குநர் மாதிரி தரவு)"""
}

def generate_idempotency_key(case: CaseFile) -> str:
    seed = f"{case.id}:{case.loan_id}:{case.amount_due}:{case.ptp_date or 'no_ptp'}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]

def run_action_agent(case: CaseFile) -> CaseFile:
    """
    Action Agent:
    - Generates idempotent UPI payment deep-link
    - Prepares localized WhatsApp template message
    - Updates payment_status to 'sent'
    - Handles escalation dispatch for disputes/hardships
    - Enforces demo safeguards (never real funds)
    """
    if case.status == "escalated":
        # Escalation Action: Create CRM ticket & notify human officer
        ticket_id = f"TKT-ESC-{case.id.zfill(4)}"
        case.add_trace(
            agent="Action",
            action="Case Escalation Dispatched to Human Officer",
            summary=f"Created CRM Ticket #{ticket_id}. Routed to {case.assigned_human or 'Floor Manager'} with complete call audio & transcript."
        )
        return case

    # Generate Idempotent payment link if not already created
    if not case.payment_link:
        idem_key = generate_idempotency_key(case)
        case.payment_link = f"upi://pay?pa=saarthi.demolender@yesbank&pn=Demo+Lender+(Sample+Data)&am={case.amount_due:.2f}&tr={idem_key}&cu=INR"
    
    case.payment_status = "sent"

    # Localized WhatsApp template
    lang = case.language if case.language in WHATSAPP_TEMPLATES else "Hindi"
    wa_msg = WHATSAPP_TEMPLATES[lang].format(
        name=case.borrower_name,
        loan_id=case.loan_id,
        amount=f"{case.amount_due:,.2f}",
        ptp_date=case.ptp_date or "Immediate",
        link=case.payment_link
    )

    case.add_trace(
        agent="Action",
        action="Idempotent UPI Payment Link & WhatsApp Template Dispatched",
        summary=f"Generated UPI deep link ({case.payment_link[:32]}...). Composed WhatsApp message in {case.language}. Payment status set to 'SENT'."
    )

    return case
