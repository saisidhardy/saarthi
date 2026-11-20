import csv
import io
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from services.sarvam import load_pricing

FORMULA_TEXT = "Priority Score = (DPD × 2.0) + (min(Amount, 100000) / 1000) + (Broken PTPs × 15.0)"
LEGAL_WINDOW_TEXT = "08:00 - 19:00 IST (Enforces lender policy; supports RBI conduct rules)"

def parse_bool(val: Any) -> bool:
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in ("y", "yes", "true", "1", "t")

def parse_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        clean = re.sub(r"[^\d.]", "", str(val))
        return float(clean) if clean else default
    except Exception:
        return default

def parse_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        clean = re.sub(r"[^\d-]", "", str(val))
        return int(clean) if clean else default
    except Exception:
        return default

def calculate_priority_score(dpd: int, amount: float, prior_broken: int) -> float:
    """
    Deterministic, explainable formula:
    Priority Score = (DPD × 2.0) + (min(Amount, 100000) / 1000) + (Broken PTPs × 15.0)
    """
    amt_factor = min(max(amount, 0.0), 100000.0) / 1000.0
    score = (max(dpd, 0) * 2.0) + amt_factor + (max(prior_broken, 0) * 15.0)
    return round(score, 2)

def determine_call_window(preferred_time: Optional[str], dpd: int) -> str:
    """
    Determines call window inside 08:00-19:00 IST, honouring preferred_time if compliant.
    """
    if preferred_time and str(preferred_time).strip():
        pref = str(preferred_time).strip()
        # Look for hour pattern e.g. 10:30, 11am, 15:00
        time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", pref, re.IGNORECASE)
        if time_match:
            hr = int(time_match.group(1))
            meridiem = (time_match.group(3) or "").lower()
            if meridiem == "pm" and hr < 12:
                hr += 12
            elif meridiem == "am" and hr == 12:
                hr = 0
            
            if 8 <= hr < 19:
                return f"{pref} (Honouring borrower preference)"
            else:
                return f"10:00 - 12:00 IST (Preferred '{pref}' outside 08:00-19:00 IST window)"

    # Default policy daytime windows by DPD tier
    if dpd <= 7:
        return "10:00 - 12:00 IST (Morning reminder window)"
    elif dpd <= 15:
        return "14:00 - 16:30 IST (Mid-day resolution window)"
    else:
        return "16:30 - 18:30 IST (Evening pre-close window)"

def generate_call_plan_from_csv(csv_content: str) -> Dict[str, Any]:
    """
    Dry run call plan generator:
    - Input: CSV content
    - Output per account: priority rank, explainable score, call window, offer range, DNC flags, est cost
    - Summary counts and export CSV
    """
    pricing = load_pricing()
    rates = pricing.get("rates", {})
    # Est per-call: 2.0 min STT + 700 chars TTS
    stt_rate = rates.get("stt_cost_per_minute", 0.49)
    tts_rate = rates.get("tts_cost_per_1000_chars", 1.00)
    est_cost_per_call = round((2.0 * stt_rate) + (0.7 * tts_rate), 2)  # ₹1.68

    reader = csv.DictReader(io.StringIO(csv_content.strip()))
    
    accounts = []
    for idx, row in enumerate(reader):
        account_id = str(row.get("account_id") or row.get("id") or f"ACC-{idx+1}").strip()
        name = str(row.get("name") or row.get("borrower_name") or f"Borrower {idx+1}").strip()
        phone_masked = str(row.get("phone_masked") or row.get("phone") or "XXXXXX0000").strip()
        if len(phone_masked) > 6 and not phone_masked.startswith("X"):
            phone_masked = phone_masked[:3] + "XXXXXX" + phone_masked[-4:]
        
        amount_due = parse_float(row.get("amount_due") or row.get("amount"), 10000.0)
        dpd = parse_int(row.get("dpd"), 3)
        language = str(row.get("language") or "Hindi").strip()
        preferred_time = row.get("preferred_time")
        prior_broken = parse_int(row.get("prior_broken_ptps"), 0)
        sensitive_event = parse_bool(row.get("sensitive_event"))
        paid_today = parse_bool(row.get("paid_today"))
        daily_cap_reached = parse_bool(row.get("daily_cap_reached"))

        # Explainable score
        score = calculate_priority_score(dpd, amount_due, prior_broken)
        call_window = determine_call_window(preferred_time, dpd)
        
        # Policy-allowed offer range
        min_part = round(amount_due * 0.30, 2)
        offer_range = {
            "max_extension_days": 7,
            "min_part_payment_amount": min_part,
            "summary": f"Max 7 days extension, min part-payment ₹{min_part:,.2f} (30%)"
        }

        # DNC Evaluation
        dnc_rule = None
        status = "CALL"
        reason = "Eligible for today's outreach"
        cost = est_cost_per_call

        if sensitive_event:
            status = "HOLD"
            dnc_rule = "RULE-DNC-SENS01"
            reason = "Hold: Sensitive life event active (7-day pause per FAIR-PRAC-SENS01)"
            cost = 0.0
        elif paid_today:
            status = "HOLD"
            dnc_rule = "RULE-DNC-PAID01"
            reason = "Hold: Payment already received today"
            cost = 0.0
        elif daily_cap_reached:
            status = "HOLD"
            dnc_rule = "RULE-DNC-CAP01"
            reason = "Hold: Maximum contact attempts (2 calls/day) reached for today"
            cost = 0.0
        elif prior_broken >= 3:
            status = "ESCALATE"
            dnc_rule = "RULE-DNC-RECIDIVIST01"
            reason = "Escalate: Repeated broken promises (>=3); handover to senior credit desk"
            cost = 0.0

        accounts.append({
            "account_id": account_id,
            "name": name,
            "phone_masked": phone_masked,
            "amount_due": amount_due,
            "dpd": dpd,
            "language": language,
            "priority_score": score,
            "status": status,
            "best_call_window": call_window,
            "offer_range": offer_range,
            "dnc_flag": dnc_rule,
            "reason": reason,
            "estimated_cost_inr": cost,
            "prior_broken_ptps": prior_broken
        })

    # Sort callable accounts by priority_score descending, followed by escalated, then hold
    accounts.sort(key=lambda x: (0 if x["status"] == "CALL" else (1 if x["status"] == "ESCALATE" else 2), -x["priority_score"]))

    # Assign priority rank 1..N
    for rank, acc in enumerate(accounts, start=1):
        acc["priority_rank"] = rank

    calls_count = sum(1 for a in accounts if a["status"] == "CALL")
    holds_count = sum(1 for a in accounts if a["status"] == "HOLD")
    escalate_count = sum(1 for a in accounts if a["status"] == "ESCALATE")
    total_cost = round(sum(a["estimated_cost_inr"] for a in accounts), 2)

    return {
        "formula": FORMULA_TEXT,
        "legal_window_rule": LEGAL_WINDOW_TEXT,
        "summary": {
            "total_accounts": len(accounts),
            "accounts_to_call": calls_count,
            "accounts_to_hold": holds_count,
            "accounts_to_escalate": escalate_count,
            "estimated_total_cost_inr": total_cost,
            "cost_per_contact_rate": est_cost_per_call,
            "cost_label": "estimated"
        },
        "plan": accounts
    }

def export_call_plan_csv(plan_data: Dict[str, Any]) -> str:
    """
    Exports computed call plan to CSV string.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "priority_rank",
        "account_id",
        "name",
        "phone_masked",
        "priority_score",
        "status",
        "amount_due",
        "dpd",
        "language",
        "best_call_window",
        "min_part_payment_inr",
        "max_extension_days",
        "dnc_rule_id",
        "reason",
        "estimated_cost_inr"
    ])
    for a in plan_data.get("plan", []):
        writer.writerow([
            a.get("priority_rank"),
            a.get("account_id"),
            a.get("name"),
            a.get("phone_masked"),
            a.get("priority_score"),
            a.get("status"),
            a.get("amount_due"),
            a.get("dpd"),
            a.get("language"),
            a.get("best_call_window"),
            a.get("offer_range", {}).get("min_part_payment_amount"),
            a.get("offer_range", {}).get("max_extension_days"),
            a.get("dnc_flag") or "NONE",
            a.get("reason"),
            a.get("estimated_cost_inr")
        ])
    return output.getvalue()
