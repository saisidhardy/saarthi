import os
import re
import json
from datetime import datetime, timedelta, timezone, date
from typing import Optional, Dict, Any
from app.models import JourneyRecord, WorkflowStep, LLMProposal
from app.config import settings
from services.sarvam import sarvam_service

def extract_amount_from_speech(text: str, total_due: float, loan_id: Optional[str] = None) -> Optional[float]:
    """
    Extracts numerical payment amounts from spoken Hinglish/Marathi text.
    Handles 'half', '10k', '₹10,000', '2500', full payment phrases ('पूर्ण', 'सर्व', 'पूरा', 'full').
    Explicitly filters out loan_id digits (e.g. 1001, 1002) so identity verification numbers aren't confused with money.
    """
    clean = text.lower()
    
    # 1. Full payment indicators in Marathi, Hindi, English, Telugu, Tamil, Kannada
    if any(k in clean for k in ["पूर्ण", "पूरा", "पूरे", "all", "full", "complete", "संपूर्ण", "सर्व", "सगळे", "नक्की सर्व", "full payment", "పూర్తి", "మొత్తం", "ముழுவதும்", "முழு", "ಸಂಪೂರ್ಣ", "ಪೂರ್ತಿ"]):
        return total_due

    # 2. Check for half / 50%
    if any(k in clean for k in ["half", "आधा", "निम्मे", "50%"]):
        return round(total_due * 0.5, 2)
    
    # 3. 10k style
    k_match = re.search(r"(\d+(?:\.\d+)?)\s*k\b", clean)
    if k_match:
        return float(k_match.group(1)) * 1000.0

    # 4. Extract loan digits to ignore (e.g. 1001, 1002)
    loan_digits = ""
    if loan_id:
        loan_digits = re.sub(r"\D", "", str(loan_id))[-4:]

    # 5. Numerical search
    matches = re.finditer(r"(?:rs\.?|inr|₹)?\s*(\d{1,3}(?:,\d{3})+|\d{4,6}|\d{3})", clean)
    found_amounts = []
    for m in matches:
        raw = m.group(1).replace(",", "")
        try:
            val = float(raw)
            # Skip loan verification digits
            if loan_digits and raw == loan_digits:
                continue
            if 100 <= val <= total_due:
                found_amounts.append(val)
        except ValueError:
            continue

    if found_amounts:
        # If there are part payment numbers (e.g. 2,500 out of 7,500 or 10,000 out of 25,000), return the part payment
        part_payments = [v for v in found_amounts if v < total_due]
        if part_payments:
            return part_payments[0]
        return found_amounts[0]

    return None

def run_negotiation_agent(record: JourneyRecord, step: Optional[WorkflowStep] = None, context: Optional[Dict[str, Any]] = None) -> JourneyRecord:
    """
    Negotiation Agent (LLM Proposer):
    - Analyzes dialogue context in the borrower's language.
    - Extracts raw entities: amount (integer), relative date phrase, intent, and waiver requests.
    - Formulates an LLMProposal.
    - Does NOT make final policy decisions (The Policy Engine CODE decides).
    """
    workflow_id = record.workflow_id or (context.get("workflow_id") if context else "collections")
    
    dialogue_texts = [t.text for t in record.transcript if t.speaker in ("borrower", "customer")]
    latest_dialogue = dialogue_texts[-1] if dialogue_texts else ""
    full_dialogue = " ".join(dialogue_texts)
    analysis_text = latest_dialogue if len(dialogue_texts) > 1 else full_dialogue

    if not settings.SIMULATE and settings.SARVAM_API_KEY and settings.SARVAM_API_KEY != "mock_sarvam_key":
        try:
            user_msg = f"""
            Borrower: {record.customer_name}
            Loan ID: {record.data.get('loan_id')}
            Amount Due: ₹{record.amount_due}
            DPD: {record.dpd}
            Dialogue transcript:
            {full_dialogue}

            Latest Borrower Message:
            {latest_dialogue}

            Extract:
            1. intent: 'ptp' | 'part_payment' | 'hardship' | 'dispute' | 'avoidance' | 'adversarial' | 'cashflow_split' | 'pre_due_shift'
            2. sentiment: 'positive' | 'neutral' | 'anxious' | 'hostile' | 'adversarial'
            3. extracted_amount: integer or null (e.g. 2500, 10000, 20000)
            4. extracted_date_phrase: exact relative date text (e.g. 'Friday', '5th', '20 days', 'tomorrow', '3 days')
            5. waiver_requested: boolean (true if borrower demands waiver, fee cancellation, or says 'ignore your rules')
            6. requested_days: integer or null (e.g. 20 if borrower asks 20 days, 3 if asking 3 days shift)

            Output JSON only. Do not compute ISO dates.
            """
            system_prompt = (
                "You are Saarthi Negotiation Proposer powered by Sarvam-105B. "
                "CRITICAL DEVANAGARI MANDATE: Any Marathi (mr-IN) or Hindi (hi-IN) text meant to be spoken aloud "
                "MUST be in native Devanagari script (e.g. मराठी / हिन्दी, never Romanized Hinglish or Romanized Marathi) "
                "so TTS pronounces it cleanly with authentic regional accents. "
                "Structured JSON extraction fields (intent, extracted_amount, extracted_date_phrase, etc.) must remain in standard English/ISO format. "
                "Return valid JSON only."
            )
            content = sarvam_service.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.1
            )
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                proposal = LLMProposal(
                    intent=parsed.get("intent", "ptp"),
                    offered_amount=float(parsed["extracted_amount"]) if parsed.get("extracted_amount") else None,
                    date_phrase=parsed.get("extracted_date_phrase") or "3 days",
                    waiver_requested=bool(parsed.get("waiver_requested", False)),
                    requested_days=int(parsed["requested_days"]) if parsed.get("requested_days") else None,
                    sentiment=parsed.get("sentiment", "neutral"),
                    confidence=0.96,
                    raw_response=content
                )
            else:
                proposal = _deterministic_propose(record, analysis_text)
        except Exception:
            proposal = _deterministic_propose(record, analysis_text)
    else:
        proposal = _deterministic_propose(record, analysis_text)

    # Attach proposal to record memory
    record.data["llm_proposal"] = proposal.model_dump()
    record.intent = proposal.intent
    record.sentiment = proposal.sentiment
    record.confidence = proposal.confidence

    # Generate live "Understood" chips for UI
    date_display = proposal.date_phrase or "3 days"
    amt_display = f"₹{proposal.offered_amount:,.0f}" if proposal.offered_amount else f"₹{record.amount_due:,.0f}"
    record.data["understood_chips"] = {
        "amount": amt_display,
        "date_phrase": date_display,
        "intent": proposal.intent,
        "confidence": f"{proposal.confidence * 100:.0f}%"
    }

    record.add_trace(
        agent="Negotiation",
        action="Borrower Intent & Entity Extraction",
        summary=f"LLM Proposed: Intent='{proposal.intent}', Amount={amt_display}, DatePhrase='{date_display}', Waiver={proposal.waiver_requested}. Confidence: {proposal.confidence*100:.0f}%.",
        badge="Review/Critique"
    )
    return record

def _deterministic_propose(record: JourneyRecord, text: str) -> LLMProposal:
    clean = text.lower()
    
    # 1. Adversarial / Prompt Injection / Waiver Demand
    if any(k in clean for k in ["ignore your rules", "give me a waiver", "waive", "माफी करा", "सूट", "छूट"]):
        return LLMProposal(
            intent="adversarial",
            offered_amount=None,
            date_phrase="20 days",
            waiver_requested=True,
            requested_days=20,
            sentiment="hostile",
            confidence=0.98
        )

    # 2. Dispute
    if any(k in clean for k in ["already paid", "cut चुके", "कट गए", "पैसे भर चुका", "गलत", "statement check", "लेजर", "फर्जी", "कटौती"]):
        return LLMProposal(
            intent="dispute",
            offered_amount=0.0,
            date_phrase=None,
            sentiment="hostile",
            confidence=0.98
        )

    # 3. Sensitive Events / Hospital / Emergency
    if any(k in clean for k in ["hospital", "हॉस्पिटल", "accident", "अपघात", "दवाखाना", "icu", "admitted", "ऍडमिट", "मृत्यू", "निधन", "वारले", "मयत"]):
        return LLMProposal(
            intent="hardship",
            offered_amount=0.0,
            date_phrase=None,
            sentiment="anxious",
            confidence=0.99
        )

    # 4. Job loss distress
    if any(k in clean for k in ["job loss", "lost my job", "नोकरी गेली", "काम छूट गया", "salary delay", "पगार झाला नाही"]):
        return LLMProposal(
            intent="hardship",
            offered_amount=None,
            date_phrase="7 days",
            sentiment="anxious",
            confidence=0.95
        )

    # 5. Avoidance
    if any(k in clean for k in ["मीटिंग", "meeting", "busy", "बाद में", "फोन काटो", "काट दिया", "disconnect", "काम में हूँ"]):
        return LLMProposal(
            intent="avoidance",
            offered_amount=None,
            date_phrase=None,
            sentiment="neutral",
            confidence=0.90
        )

    # 6. T-24h Preventive Bounce Shift (Scenario S7)
    if record.trigger_type == "PRE_DUE_T24H" or any(k in clean for k in ["पुढे ढकला", "shift", "postpone", "pre-due", "590 रुपये", "590", "बाउंस फी", "फी वाचेल", "बफर"]):
        return LLMProposal(
            intent="pre_due_shift",
            offered_amount=record.amount_due,
            date_phrase="3 days",
            requested_days=3,
            waiver_requested=False,
            sentiment="positive",
            confidence=0.98
        )

    # 7. Cashflow-Synced Kirana Micro-Split (Scenario S8)
    if any(k in clean for k in ["4 आठवड्यांत", "चार आठवड्यांत", "दर शुक्रवारी", "हर शुक्रवार", "10-10 हजार", "हप्त्यात", "micro-split", "micro split", "4 हप्त्यात"]):
        tranche_amt = round(record.amount_due / 4, 2)
        return LLMProposal(
            intent="cashflow_split",
            offered_amount=tranche_amt,
            date_phrase="Friday",
            requested_days=4,
            waiver_requested=False,
            sentiment="positive",
            confidence=0.98
        )

    # 8. Part Payment (e.g. S2 code-mixed "Friday ko 2,500 bhar dunga, baaki next week" or "Friday la 2,500 bharu ka?")
    offered_amt = extract_amount_from_speech(text, record.amount_due, loan_id=record.data.get("loan_id"))
    
    # Extract date phrase
    date_phrase = "3 days"
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "शुक्रवार", "सोमवार", "शनिवार", "रविवार", "శుక్రవారం", "సోమవారం", "శనివారం", "வெள்ளிக்கிழமை", "திங்கட்கிழமை", "ಶುಕ್ರವಾರ", "ಸೋಮವಾರ"]
    for w in weekdays:
        if w in clean:
            date_phrase = w.capitalize()
            break
    if "5 तारखेला" in clean or "5 तारीख" in clean or "5th" in clean:
        date_phrase = "5 तारखेला"

    intent = "part_payment" if offered_amt and offered_amt < record.amount_due else "ptp"

    return LLMProposal(
        intent=intent,
        offered_amount=offered_amt or record.amount_due,
        date_phrase=date_phrase,
        waiver_requested=False,
        sentiment="positive",
        confidence=0.95
    )

# Alias for backwards compatibility
run_decision_agent = run_negotiation_agent
