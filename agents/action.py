import hashlib
from typing import Optional, Dict, Any
from app.models import JourneyRecord, WorkflowStep

COLLECTIONS_WHATSAPP_TEMPLATES = {
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
சாரதி ஃபைனான்சியலில் பேசியதற்கு நன்றி. கடன் கணக்கு {loan_id}-க்கான ₹{amount} PTP பதிவு செய்யப்பட்டது: {link}"""
}

SALES_WHATSAPP_TEMPLATES = {
    "Marathi": """प्रिय {name}जी,
सारथी कॅपिटलकडून अभिनंदन! आपले ₹{amount} चे प्री-अ‍ॅप्रूव्हड पर्सनल लोन मंजूर झाले आहे. 

केवळ २ मिनिटांत रक्कम खात्यात मिळवण्यासाठी खालील लिंकवरून कागदपत्रे अपलोड करा:
{link}
आवश्यक कागदपत्रे: १) आधार कार्ड २) पॅन कार्ड ३) ३ महिन्यांचे बँक स्टेटमेंट.

(टीप: Demo sample data)""",

    "Hindi": """प्रिय {name} जी,
सारथी कैपिटल से बधाई! आपका ₹{amount} का प्री-अप्रूव्ड पर्सनल लोन स्वीकृत हो चुका है।

तुरंत डिजिटल डिस्बर्सल के लिए नीचे दिए गए लिंक से दस्तावेज़ सबमिट करें:
{link}
आवश्यक दस्तावेज: 1) आधार 2) पैन कार्ड 3) 3 महीने का बैंक स्टेटमेंट।

(नोट: Demo lender sample data)""",

    "English": """Dear {name},
Congratulations from Saarthi Capital! Your pre-approved personal loan of ₹{amount} is ready for instant disbursal.

Complete 1-click verification here:
{link}
Required documents: 1) PAN 2) Aadhaar 3) 3-month Bank Statement.

(Note: Demo lender sample data)"""
}

def generate_idempotency_key(record: JourneyRecord) -> str:
    seed = f"{record.id}:{record.data.get('loan_id') or 'lead'}:{record.amount_due or record.data.get('preapproved_amount')}:{record.ptp_date or 'none'}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]

def run_action_agent(record: JourneyRecord, step: Optional[WorkflowStep] = None, context: Optional[Dict[str, Any]] = None) -> JourneyRecord:
    """
    Generic Action Agent:
    - Generates idempotent transaction/application links
    - Prepares localized WhatsApp template message
    - Updates payment / application status
    - Handles escalation dispatch for disputes/hardships
    """
    workflow_id = record.workflow_id or (context.get("workflow_id") if context else "collections")

    # If already escalated in collections or sales
    if record.status == "escalated":
        ticket_id = f"TKT-ESC-{record.id.zfill(4)}"
        record.add_trace(
            agent="Action",
            action="Case Escalation Dispatched to Human Officer",
            summary=f"Created CRM Ticket #{ticket_id}. Routed to {record.assigned_human or 'Floor Manager'} with complete transcript & context."
        )
        return record

    idem_key = generate_idempotency_key(record)

    if workflow_id == "loan_sales":
        # Loan Sales Action
        pre_amt = float(record.data.get("preapproved_amount", 250000.0))
        app_link = f"https://apply.saarthi.demo/loan/{idem_key}?amt={pre_amt:.0f}"
        record.data["application_link"] = app_link
        record.data["docs_requested"] = ["Aadhaar", "PAN Card", "3-Month Bank Statement"]
        record.status = "qualified"

        lang = record.language if record.language in SALES_WHATSAPP_TEMPLATES else "Hindi"
        wa_msg = SALES_WHATSAPP_TEMPLATES[lang].format(
            name=record.customer_name,
            amount=f"{pre_amt:,.0f}",
            link=app_link
        )
        record.data["whatsapp_message"] = wa_msg

        record.add_trace(
            agent="Action",
            action="Pre-Approved Loan Sanction & Document Checklist Dispatched",
            summary=f"Issued Digital Application Link ({app_link[:32]}...). WhatsApp document checklist dispatched in {record.language}."
        )
        return record

    # Collections Action
    if not record.payment_link:
        record.payment_link = f"upi://pay?pa=saarthi.demolender@yesbank&pn=Demo+Lender+(Sample+Data)&am={record.amount_due:.2f}&tr={idem_key}&cu=INR"
    
    record.payment_status = "sent"

    lang = record.language if record.language in COLLECTIONS_WHATSAPP_TEMPLATES else "Hindi"
    wa_msg = COLLECTIONS_WHATSAPP_TEMPLATES[lang].format(
        name=record.customer_name,
        loan_id=record.data.get("loan_id", "LN-GEN"),
        amount=f"{record.amount_due:,.2f}",
        ptp_date=record.ptp_date or "Immediate",
        link=record.payment_link
    )
    record.data["whatsapp_message"] = wa_msg

    record.add_trace(
        agent="Action",
        action="Idempotent UPI Payment Link & WhatsApp Template Dispatched",
        summary=f"Generated UPI deep link ({record.payment_link[:32]}...). Composed WhatsApp message in {record.language}. Payment status set to 'SENT'."
    )

    return record
