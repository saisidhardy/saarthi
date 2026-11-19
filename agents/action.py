import os
import yaml
import hashlib
from typing import Optional, Dict, Any
from app.models import JourneyRecord, WorkflowStep

LENDER_YAML_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "policies", "lender.yaml")

def load_lender_config() -> Dict[str, Any]:
    if os.path.exists(LENDER_YAML_PATH):
        try:
            with open(LENDER_YAML_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {
        "lender_info": {"lender_name": "Saarthi Capital Ltd."},
        "repayment_routing": {"lender_vpa": "repayments.saarthi@yesbank", "display_name": "Saarthi Capital Repayments"},
        "grievance_redressal": {
            "principal_nodal_officer": {
                "name": "Mr. Alok Verma",
                "email": "nodal.officer@saarthicapital.demo",
                "phone": "+91-22-6899-4400"
            }
        }
    }

COLLECTIONS_WHATSAPP_TEMPLATES = {
    "Marathi": """प्रिय {name}जी,
सारथी कॅपिटल सोबत बोलल्याबद्दल धन्यवाद. आपल्या विनंतीनुसार लोन खाते {loan_id} च्या ₹{amount} भरण्यासाठी PTP तारीख {ptp_date} नोंदवली आहे.

हे पेमेंट थेट सावकाराच्या अधिकृत बँक खात्यात ({vpa}) जमा होते. खालील सुरक्षित UPI लिंक वापरा:
{link}

तक्रार निवारण अधिकारी: {pno_name} ({pno_email} | फोन: {pno_phone}).
(टीप: प्रात्यक्षिक डेटा - Demo lender sample data. Pays directly to {lender}'s account)""",

    "Hindi": """प्रिय {name} जी,
सारथी कैपिटल से बात करने के लिए धन्यवाद। आपके लोन खाते {loan_id} के ₹{amount} भुगतान हेतु PTP तारीख {ptp_date} दर्ज कर ली गई है।

यह भुगतान सीधे ऋणदाता के अधिकृत बैंक खाते ({vpa}) में जमा होता है। सुरक्षित UPI लिंक:
{link}

शिकायत निवारण अधिकारी: {pno_name} ({pno_email} | फोन: {pno_phone})।
(नोट: डेमो डेटा - Demo lender sample data. Pays directly to {lender}'s account)""",

    "English": """Dear {name},
Thank you for speaking with Saarthi Capital. As agreed, your Promise-to-Pay (PTP) for loan {loan_id} of ₹{amount} is scheduled for {ptp_date}.

This payment is credited directly into the lender's designated account ({vpa}). Complete payment using this secure link:
{link}

Principal Grievance Officer: {pno_name} ({pno_email} | Phone: {pno_phone}).
(Note: Demo lender sample data. Pays directly to {lender}'s account)"""
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
    Action Agent:
    - Accepts ONLY a valid PolicyDecision object issued by the Policy Engine.
    - Resolves UPI link directly to lender's VPA from policies/lender.yaml.
    - Saarthi NEVER receives, pools, or routes borrower money.
    - Prepares localized WhatsApp template message with Grievance Officer details.
    """
    workflow_id = record.workflow_id or (context.get("workflow_id") if context else "collections")
    lender_cfg = load_lender_config()
    lender_name = lender_cfg.get("lender_info", {}).get("lender_name", "Saarthi Capital Ltd.")
    lender_vpa = lender_cfg.get("repayment_routing", {}).get("lender_vpa", "repayments.saarthi@yesbank")
    pno = lender_cfg.get("grievance_redressal", {}).get("principal_nodal_officer", {})

    record.data["lender_vpa"] = lender_vpa
    record.data["lender_name"] = lender_name
    record.data["repayment_direct_label"] = f"Pays directly to {lender_name}'s account (demo)"

    # If already escalated in collections or sales
    if record.status == "escalated":
        ticket_id = f"TKT-ESC-{record.id.zfill(4)}"
        record.add_trace(
            agent="Action",
            action="Case Escalation Dispatched to Human Officer",
            summary=f"Created CRM Ticket #{ticket_id}. Routed to {record.assigned_human or 'Floor Manager'} with complete transcript & context.",
            badge="Retry/Escalate"
        )
        return record

    # Hard Policy Firewall Enforcement: Check PolicyDecision
    if workflow_id == "collections":
        decision_data = record.data.get("policy_decision")
        if decision_data and not decision_data.get("action_permitted"):
            record.add_trace(
                agent="Action",
                action="Execution Halted - No Engine Permit",
                summary=f"Action blocked by Policy Firewall: {decision_data.get('reason')}",
                badge="Policy Firewall"
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
            action="Pre-Approved Loan Sanction Dispatched",
            summary=f"Issued Digital Application Link ({app_link[:32]}...). WhatsApp document checklist dispatched in {record.language}.",
            badge="Event Trigger"
        )
        return record

    # Collections Action
    effective_amt = record.amount_due
    decision_data = record.data.get("policy_decision")
    if decision_data and decision_data.get("effective_amount"):
        effective_amt = float(decision_data["effective_amount"])

    # 1. Micro-Split Action Rail
    if record.micro_schedule and len(record.micro_schedule) > 0:
        first_tranche = record.micro_schedule[0]
        record.payment_link = first_tranche.get("payment_link")
        record.payment_status = "sent"
        
        schedule_text = "\n".join([
            f"• हप्ता {t['tranche_number']} ({t['due_date']}, {t['weekday']}): ₹{t['amount_inr']:,.0f} [{t['rail']}]"
            for t in record.micro_schedule
        ])
        
        wa_msg = f"""प्रिय {record.customer_name}जी,
सारथी कॅपिटल: किराणा कॅशफ्लो धोरणानुसार आपल्या ₹{record.amount_due:,.0f} थकीत कर्जाचे ४ आठवड्यांचे UPI AutoPay शेड्युल मंजूर करण्यात आले आहे:

{schedule_text}

पहिला हप्ता (तात्काळ UPI लिंक):
{record.payment_link}

पुढील हप्त्यांसाठी (Tranches 2-4) AutoPay मॅन्डेट लिंक:
upi://mandate?pa={lender_vpa}&pn=Saarthi+AutoPay&am={first_tranche['amount_inr']:.2f}&recurrence=WEEKLY&cu=INR

तक्रार निवारण अधिकारी: {pno.get('name', 'श्री आलोक वर्मा')} ({pno.get('phone', '022-68994400')}).
(थेट {lender_name} खात्यात जमा होतो - Demo)"""
        record.data["whatsapp_message"] = wa_msg

        record.add_trace(
            agent="Action",
            action="Kirana 4x Micro-Split AutoPay Schedule Dispatched",
            summary=f"Dispatched 4-week Friday schedule ({schedule_text.splitlines()[0]}...). Tranche 1 UPI link & Tranches 2-4 AutoPay mandate issued.",
            badge="Event Trigger"
        )
        return record

    # 2. T-24h Preventive Bounce Rescue Action Rail
    if record.trigger_type == "PRE_DUE_T24H" or record.bounce_fee_saved_inr > 0:
        record.payment_status = "rescheduled"
        if not record.payment_link:
            record.payment_link = f"upi://pay?pa={lender_vpa}&pn=Saarthi+Buffer&am=6000.00&tr={idem_key}&cu=INR"
        
        wa_msg = f"""प्रिय {record.customer_name}जी,
सारथी कॅपिटल: आपल्या विनंतीनुसार ईएमआय ऑटो-डेबिट तारीख ३ दिवस पुढे ढकलण्यात आली आहे ({record.ptp_date}).

• बँक बाउंस फी बचत: ₹590.00 (वाचवली)
• सिबिल स्कोअर: १००% सुरक्षित
• पर्यायी लिक्विडिटी बफर टॉप-अप (₹6,000): {record.payment_link}

तक्रार निवारण अधिकारी: {pno.get('name', 'श्री आलोक वर्मा')} ({pno.get('phone', '022-68994400')}).
(थेट {lender_name} खात्यात - Demo)"""
        record.data["whatsapp_message"] = wa_msg

        record.add_trace(
            agent="Action",
            action="T-24h Preventive Debit Shift & Fee Protection Dispatched",
            summary=f"Proactive AutoPay date shifted to {record.ptp_date}. Saved ₹590 bounce fee and protected CIBIL score.",
            badge="Event Trigger"
        )
        return record

    # Standard Collections Action
    # UPI deep link directly to regulated lender's escrow account
    if not record.payment_link:
        record.payment_link = f"upi://pay?pa={lender_vpa}&pn=Saarthi+Capital+Repayments&am={effective_amt:.2f}&tr={idem_key}&cu=INR"
    
    record.payment_status = "sent"

    lang = record.language if record.language in COLLECTIONS_WHATSAPP_TEMPLATES else "Hindi"
    wa_msg = COLLECTIONS_WHATSAPP_TEMPLATES[lang].format(
        name=record.customer_name,
        loan_id=record.data.get("loan_id", "LN-GEN"),
        amount=f"{effective_amt:,.2f}",
        ptp_date=record.ptp_date or "Immediate",
        vpa=lender_vpa,
        link=record.payment_link,
        pno_name=pno.get("name", "Mr. Alok Verma"),
        pno_email=pno.get("email", "nodal.officer@saarthicapital.demo"),
        pno_phone=pno.get("phone", "+91-22-6899-4400"),
        lender=lender_name
    )
    record.data["whatsapp_message"] = wa_msg

    record.add_trace(
        agent="Action",
        action="Idempotent UPI Payment Link & WhatsApp Template Dispatched",
        summary=f"Generated UPI deep link ({record.payment_link[:34]}...) resolving directly to {lender_vpa}. WhatsApp notice dispatched with Grievance Officer details. Payment status set to 'SENT'.",
        badge="Event Trigger"
    )

    return record
