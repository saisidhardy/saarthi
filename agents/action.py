import os
import hashlib
from typing import Optional, Dict, Any, List
import yaml
from app.models import JourneyRecord, WorkflowStep

LENDER_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "policies", "lender.yaml")

DEFAULT_LENDER_CONFIG = {
    "lender_info": {
        "lender_name": "Demo Lender A (Retail NBFC)",
        "cin": "U65923MH2021PLC362145"
    },
    "repayment_routing": {
        "lender_vpa": "",
        "display_name": "Demo Lender Repayments",
        "bank_name": "Demo Bank Ltd.",
        "account_type": "Designated Escrow Repayment Account"
    },
    "grievance_redressal": {
        "principal_nodal_officer": {
            "name": "Mr. Alok Verma",
            "phone": "+91-22-6899-4400"
        }
    }
}

def load_lender_config() -> Dict[str, Any]:
    if os.path.exists(LENDER_FILE):
        try:
            with open(LENDER_FILE, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or DEFAULT_LENDER_CONFIG
        except Exception:
            pass
    return DEFAULT_LENDER_CONFIG

def generate_idempotency_key(record: JourneyRecord) -> str:
    raw = f"{record.id}-{record.workflow_id}-{record.status}-{record.ptp_date or 'none'}-{record.version}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

COLLECTIONS_WHATSAPP_TEMPLATES = {
    "Marathi": (
        "प्रिय {name}जी,\n"
        "{lender_name}: आपल्या कर्जाचा थकीत हप्ता ₹{amount} साठी {ptp_date} ची तारीख नोंदवली आहे.\n"
        "{payment_block}\n"
        "तक्रार निवारण: {nodal_name} ({nodal_phone}).\n"
        "(थेट {lender_name} खात्यात - Demo)"
    ),
    "Hindi": (
        "नमस्ते {name} जी,\n"
        "{lender_name}: आपके लोन बकाये ₹{amount} के लिए {ptp_date} की तारीख दर्ज की गई है।\n"
        "{payment_block}\n"
        "शिकायत निवारण: {nodal_name} ({nodal_phone}).\n"
        "(सीधे {lender_name} खाते में - Demo)"
    ),
    "English": (
        "Dear {name},\n"
        "{lender_name}: Payment commitment for overdue amount ₹{amount} has been scheduled for {ptp_date}.\n"
        "{payment_block}\n"
        "Grievance Officer: {nodal_name} ({nodal_phone}).\n"
        "(Direct to {lender_name} account - Demo)"
    )
}

SALES_WHATSAPP_TEMPLATES = {
    "Hindi": (
        "बधाई हो {name} जी! आप ₹{amount} के पूर्व-स्वीकृत व्यक्तिगत ऋण के लिए पात्र हैं।\n"
        "डिजिटल आवेदन पूरा करने के लिए यहाँ क्लिक करें: {link}\n"
        "आवश्यक दस्तावेज: आधार, पैन कार्ड, बैंक विवरण। (Demo)"
    ),
    "Marathi": (
        "अभिनंदन {name}जी! आपण ₹{amount} च्या पूर्व-मंजूर वैयक्तिक कर्जासाठी पात्र आहात.\n"
        "डिजिटल अर्ज पूर्ण करण्यासाठी येथे क्लिक करा: {link}\n"
        "कागदपत्रे: आधार, पॅन, बँक स्टेटमेंट. (Demo)"
    ),
    "English": (
        "Congratulations {name}! You qualify for a pre-approved personal loan of ₹{amount}.\n"
        "Click to complete digital application: {link}\n"
        "Documents required: Aadhaar, PAN Card, Bank Statement. (Demo)"
    )
}

def run_action_agent(
    record: JourneyRecord,
    step: Optional[WorkflowStep] = None,
    context: Optional[Dict[str, Any]] = None
) -> JourneyRecord:
    """
    Action Agent (Execution & Settlement Dispatch):
    - Enforces lender policy (demo); supports RBI conduct rules.
    - If lender_vpa is unset, disables upi:// link and sets simulate_payment_only = True.
    - Saarthi NEVER receives, pools, or routes borrower money.
    """
    workflow_id = record.workflow_id or (context.get("workflow_id") if context else "collections")
    lender_cfg = load_lender_config()
    lender_name = lender_cfg.get("lender_info", {}).get("lender_name", "Demo Lender A (Retail NBFC)")
    lender_vpa = lender_cfg.get("repayment_routing", {}).get("lender_vpa", "")
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
        pre_amt = float(record.data.get("preapproved_amount", 250000.0))
        app_link = f"https://apply.demolender.example/loan/{idem_key}?amt={pre_amt:.0f}"
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

    # Build UPI link only if valid lender_vpa is set in lender.yaml
    payment_link = None
    if lender_vpa and lender_vpa.strip():
        payment_link = f"upi://pay?pa={lender_vpa}&pn={lender_name.replace(' ', '+')}&am={effective_amt:.2f}&tr={idem_key}&cu=INR"
    
    record.payment_link = payment_link
    record.data["payment_link"] = payment_link
    record.data["simulate_payment_only"] = (payment_link is None)

    # 1. Micro-Split Action Rail
    if record.micro_schedule and len(record.micro_schedule) > 0:
        first_tranche = record.micro_schedule[0]
        record.payment_link = first_tranche.get("payment_link")
        record.payment_status = "sent"
        
        schedule_text = "\n".join([
            f"• हप्ता {t['tranche_number']} ({t['due_date']}, {t['weekday']}): ₹{t['amount_inr']:,.0f}"
            for t in record.micro_schedule
        ])
        
        payment_notice = f"पेमेंट लिंक: {record.payment_link}" if record.payment_link else "पेमेंट सिम्युलेटर उपलब्ध आहे."
        wa_msg = f"""प्रिय {record.customer_name}जी,
{lender_name}: आपल्या ₹{record.amount_due:,.0f} थकीत कर्जाचे ४ आठवड्यांचे शेड्युल नोंदवले आहे:

{schedule_text}

{payment_notice}
(मॅन्डेट विनंती पाठवली आहे; तुम्ही UPI ॲपमध्ये मंजूर केल्यावरच सक्रिय होईल; तुम्ही ते कधीही रद्द करू शकता)

तक्रार निवारण अधिकारी: {pno.get('name', 'श्री आलोक वर्मा')} ({pno.get('phone', '022-68994400')}).
(थेट {lender_name} खात्यात - Demo)"""
        record.data["whatsapp_message"] = wa_msg

        record.add_trace(
            agent="Action",
            action="Micro-Split Schedule Dispatched",
            summary=f"Dispatched 4-week Friday schedule. Mandate request sent; becomes active only when borrower approves in UPI app.",
            badge="Event Trigger"
        )
        return record

    # 2. T-24h Preventive Intervention Action Rail
    if record.trigger_type == "PRE_DUE_T24H":
        record.payment_status = "rescheduled"
        payment_notice = f"पर्यायी टोकन लिंक: {record.payment_link}" if record.payment_link else "पेमेंट सिम्युलेटर उपलब्ध आहे."
        wa_msg = f"""प्रिय {record.customer_name}जी,
{lender_name}: आपल्या विनंतीनुसार ईएमआय तारीख ३ दिवस पुढे ढकलण्यात आली आहे ({record.ptp_date}).

{payment_notice}

तक्रार निवारण अधिकारी: {pno.get('name', 'श्री आलोक वर्मा')} ({pno.get('phone', '022-68994400')}).
(थेट {lender_name} खात्यात - Demo)"""
        record.data["whatsapp_message"] = wa_msg

        record.add_trace(
            agent="Action",
            action="T-24h Preventive Debit Shift Dispatched",
            summary=f"Payment schedule shifted to {record.ptp_date} per lender policy.",
            badge="Event Trigger"
        )
        return record

    # Standard Collections Action
    record.payment_status = "sent"

    lang = record.language if record.language in COLLECTIONS_WHATSAPP_TEMPLATES else "Hindi"
    payment_block = f"सुरक्षित पेमेंट लिंक: {record.payment_link}" if record.payment_link else "सुरक्षित पेमेंट सिम्युलेटर लिंक सक्रिय आहे."
    wa_msg = COLLECTIONS_WHATSAPP_TEMPLATES[lang].format(
        name=record.customer_name,
        lender_name=lender_name,
        amount=f"{effective_amt:,.2f}",
        ptp_date=record.ptp_date or "Immediate",
        payment_block=payment_block,
        nodal_name=pno.get("name", "Mr. Alok Verma"),
        nodal_phone=pno.get("phone", "+91-22-6899-4400")
    )
    record.data["whatsapp_message"] = wa_msg

    record.add_trace(
        agent="Action",
        action="Settlement Details Dispatched",
        summary=f"Settlement details dispatched for {record.customer_name}. Enforces lender policy (demo); supports RBI conduct rules.",
        badge="Event Trigger"
    )

    return record
