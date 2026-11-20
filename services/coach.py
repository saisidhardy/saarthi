"""
Cash-Flow Coach Engine (Deterministic Propose-vs-Decide Pattern).
Operates strictly on synthetic Account-Aggregator-style 90-day transaction records.
Never inside a recovery call, never to pressure payment.
"""

import json
import math
import os
import yaml
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

COACH_POLICY_PATH = os.path.join(os.path.dirname(__file__), "..", "policies", "coach.yaml")
SCHEMES_POLICY_PATH = os.path.join(os.path.dirname(__file__), "..", "policies", "schemes.yaml")
PREAPPROVED_OFFERS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "preapproved_offers.json")
AA_SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "aa_samples")

# Global in-memory consent registry
# Key: persona_id -> { "consent_id": str, "granted": bool, "purpose": str, "granted_at": str, "expires_at": str }
CONSENT_REGISTRY: Dict[str, Dict[str, Any]] = {}

# Global category override registry (allows borrower to re-classify transactions or mark categories essential/flexible/ignore)
CATEGORY_OVERRIDES: Dict[str, Dict[str, str]] = {}


def load_coach_policy() -> Dict[str, Any]:
    if os.path.exists(COACH_POLICY_PATH):
        with open(COACH_POLICY_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {
        "buffer_pct": 0.15,
        "min_capacity_per_week_inr": 500.0,
        "max_capacity_share_of_inflow": 0.40,
        "taxonomy": {}
    }


def load_schemes_policy() -> Dict[str, Any]:
    if os.path.exists(SCHEMES_POLICY_PATH):
        with open(SCHEMES_POLICY_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {"schemes": [], "disclaimer": "Verify with the lender or official portal before applying."}


def load_preapproved_offers() -> List[Dict[str, Any]]:
    if os.path.exists(PREAPPROVED_OFFERS_PATH):
        with open(PREAPPROVED_OFFERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def get_available_personas() -> List[Dict[str, Any]]:
    """Returns metadata for all available synthetic Account Aggregator personas."""
    personas = []
    if os.path.exists(AA_SAMPLES_DIR):
        for fname in os.listdir(AA_SAMPLES_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(AA_SAMPLES_DIR, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        personas.append({
                            "persona_id": data.get("persona_id"),
                            "name": data.get("name"),
                            "account_type": data.get("account_type"),
                            "bank_name": data.get("bank_name"),
                            "masked_account": data.get("masked_account"),
                            "business_type": data.get("attributes", {}).get("business_type"),
                            "label": data.get("label"),
                            "transaction_count": len(data.get("transactions", []))
                        })
                except Exception:
                    continue
    return personas


def get_persona_raw_data(persona_id: str) -> Optional[Dict[str, Any]]:
    fpath = os.path.join(AA_SAMPLES_DIR, f"{persona_id}.json")
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def get_consent(persona_id: str) -> Dict[str, Any]:
    return CONSENT_REGISTRY.get(persona_id, {
        "consent_id": None,
        "granted": False,
        "status": "NOT_REQUESTED",
        "purpose": None,
        "granted_at": None,
        "expires_at": None
    })


def record_consent(persona_id: str, granted: bool, purpose: str = "AFFORDABLE_REPAYMENT_ASSESSMENT", validity_days: int = 30) -> Dict[str, Any]:
    now = datetime.now()
    consent_id = f"AA-CONSENT-{now.strftime('%Y%m%d')}-{abs(hash(persona_id)) % 100000:05d}"
    if granted:
        record = {
            "consent_id": consent_id,
            "granted": True,
            "status": "ACTIVE",
            "purpose": purpose,
            "granted_at": now.isoformat(),
            "expires_at": (now + timedelta(days=validity_days)).isoformat(),
            "regulatory_framework": "RBI Account Aggregator (AA) Framework",
            "scope": "90-day synthetic transaction records (debits/credits) for capacity calculation and scheme matching."
        }
    else:
        record = {
            "consent_id": consent_id,
            "granted": False,
            "status": "REVOKED",
            "purpose": purpose,
            "revoked_at": now.isoformat(),
            "expires_at": now.isoformat(),
            "regulatory_framework": "RBI Account Aggregator (AA) Framework",
            "scope": "No data access permitted."
        }
    CONSENT_REGISTRY[persona_id] = record
    return record


def classify_transaction(narration: str, taxonomy: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic keyword classification first; fallback heuristic for leftovers.
    The borrower can edit any category.
    """
    narr_lower = narration.lower()
    for cat_id, cat_info in taxonomy.items():
        keywords = cat_info.get("keywords", [])
        for kw in keywords:
            if kw in narr_lower:
                return {
                    "category": cat_id,
                    "display_name": cat_info.get("display_name", cat_id.title()),
                    "role": cat_info.get("default_role", "essential"),
                    "confidence": 1.0,
                    "method": "keyword_rule",
                    "matched_keyword": kw
                }
    # Leftover fallback
    return {
        "category": "other",
        "display_name": "Other Debits",
        "role": "flexible",
        "confidence": 0.50,
        "method": "heuristic_fallback",
        "matched_keyword": None
    }


def analyze_inflow_pattern(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes weekly totals, worst/best week, volatility, and day-of-week profile.
    """
    credit_txns = [t for t in transactions if t.get("type") == "CREDIT"]
    if not credit_txns:
        return {
            "total_inflow": 0.0,
            "weekly_inflows": [],
            "worst_week": None,
            "best_week": None,
            "worst_quartile_weekly_inflow": 0.0,
            "median_weekly_inflow": 0.0,
            "volatility_cv": 0.0,
            "day_of_week_profile": {}
        }

    # Group credits by 7-day calendar windows (approx 13 weeks)
    credit_txns.sort(key=lambda x: x.get("date", ""))
    start_date = datetime.strptime(credit_txns[0]["date"], "%Y-%m-%d")
    
    weeks: Dict[int, float] = {}
    day_profile: Dict[str, float] = {"Mon": 0.0, "Tue": 0.0, "Wed": 0.0, "Thu": 0.0, "Fri": 0.0, "Sat": 0.0, "Sun": 0.0}
    day_abbr = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    total_inflow = 0.0
    for t in credit_txns:
        amt = float(t.get("amount", 0.0))
        t_date = datetime.strptime(t["date"], "%Y-%m-%d")
        week_idx = (t_date - start_date).days // 7
        weeks[week_idx] = weeks.get(week_idx, 0.0) + amt
        total_inflow += amt
        day_name = day_abbr[t_date.weekday()]
        day_profile[day_name] += amt

    weekly_inflows = [round(amt, 2) for _, amt in sorted(weeks.items())]
    if not weekly_inflows:
        weekly_inflows = [0.0]

    sorted_inflows = sorted(weekly_inflows)
    n = len(sorted_inflows)
    
    # 25th percentile (worst quartile)
    q1_idx = max(0, int(n * 0.25))
    worst_quartile_inflow = sorted_inflows[q1_idx]
    
    # Median (50th percentile)
    med_idx = n // 2
    median_inflow = sorted_inflows[med_idx]

    worst_week_val = min(weekly_inflows)
    best_week_val = max(weekly_inflows)
    worst_week_idx = weekly_inflows.index(worst_week_val) + 1
    best_week_idx = weekly_inflows.index(best_week_val) + 1

    # Coefficient of variation (volatility)
    mean_inflow = sum(weekly_inflows) / len(weekly_inflows) if weekly_inflows else 1.0
    variance = sum((x - mean_inflow) ** 2 for x in weekly_inflows) / len(weekly_inflows) if weekly_inflows else 0.0
    std_dev = math.sqrt(variance)
    volatility_cv = round(std_dev / mean_inflow, 3) if mean_inflow > 0 else 0.0

    # Day of week percentages
    day_profile_pct = {}
    weekend_inflow = day_profile["Sat"] + day_profile["Sun"]
    weekend_share_pct = round((weekend_inflow / total_inflow * 100), 1) if total_inflow > 0 else 0.0
    for d, val in day_profile.items():
        day_profile_pct[d] = {
            "amount_inr": round(val, 2),
            "share_pct": round((val / total_inflow * 100), 1) if total_inflow > 0 else 0.0
        }

    peak_day = max(day_profile.items(), key=lambda x: x[1])[0]

    return {
        "total_inflow": round(total_inflow, 2),
        "weekly_inflows": weekly_inflows,
        "weeks_count": len(weekly_inflows),
        "worst_week": {"week_number": worst_week_idx, "inflow_inr": worst_week_val},
        "best_week": {"week_number": best_week_idx, "inflow_inr": best_week_val},
        "worst_quartile_weekly_inflow": round(worst_quartile_inflow, 2),
        "median_weekly_inflow": round(median_inflow, 2),
        "volatility_cv": volatility_cv,
        "weekend_share_pct": weekend_share_pct,
        "peak_day": peak_day,
        "day_of_week_profile": day_profile_pct
    }


def compute_safe_to_pay_capacity(
    worst_quartile_weekly_inflow: float,
    average_weekly_essential_outflow: float,
    buffer_pct: float = 0.15,
    min_capacity_per_week_inr: float = 500.0,
    max_capacity_share_of_inflow: float = 0.40
) -> Dict[str, Any]:
    """
    Deterministic Safe-to-Pay capacity calculation:
    capacity_per_week = worst-quartile weekly inflow - essential outflows - buffer_pct x inflow.
    The LLM never sets amounts.
    """
    safety_buffer_inr = round(worst_quartile_weekly_inflow * buffer_pct, 2)
    raw_capacity = worst_quartile_weekly_inflow - average_weekly_essential_outflow - safety_buffer_inr
    
    # Cap at maximum allowable share of inflow (e.g. 40%)
    max_allowed = round(worst_quartile_weekly_inflow * max_capacity_share_of_inflow, 2)
    capped_capacity = min(raw_capacity, max_allowed)
    
    # Floor check
    if raw_capacity <= 0:
        final_capacity = 0.0
        is_viable = False
        message = "Zero debt servicing headroom under worst-quartile cashflow; living & operating essentials exceed conservative inflows."
    else:
        final_capacity = max(min_capacity_per_week_inr, round(capped_capacity, 2))
        is_viable = True
        message = f"Conservative capacity of ₹{final_capacity:,.2f}/week established after deducting essential expenses and a {int(buffer_pct*100)}% volatility buffer."

    monthly_equivalent = round(final_capacity * 4.33, 2)

    formula_breakdown = {
        "formula": "capacity_per_week = worst_quartile_weekly_inflow - essential_outflows - (buffer_pct * worst_quartile_weekly_inflow)",
        "worst_quartile_weekly_inflow_inr": worst_quartile_weekly_inflow,
        "essential_outflows_inr": average_weekly_essential_outflow,
        "buffer_pct": buffer_pct,
        "safety_buffer_inr": safety_buffer_inr,
        "raw_capacity_inr": round(raw_capacity, 2),
        "max_allowable_cap_inr": max_allowed,
        "final_weekly_capacity_inr": final_capacity,
        "monthly_equivalent_inr": monthly_equivalent,
        "is_viable": is_viable,
        "explanation": message
    }
    return formula_breakdown


def match_government_schemes(persona_attrs: Dict[str, Any], schemes_catalog: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Matches public credit & support schemes against persona attributes.
    Outputs 'may be eligible' or 'not eligible' with deterministic reasons. Never 'approved'.
    """
    results = []
    biz_type = persona_attrs.get("business_type", "OTHER")
    is_street_vendor = persona_attrs.get("is_street_vendor", False)
    is_new_unit = persona_attrs.get("is_new_enterprise", False)
    has_udyam = persona_attrs.get("has_udyam_registration", False)
    udyam_cat = persona_attrs.get("udyam_category", "NONE")

    for scheme in schemes_catalog:
        s_id = scheme.get("id")
        eligibility = "not eligible"
        reasons = []

        if s_id == "pm_svanidhi":
            if is_street_vendor:
                eligibility = "may be eligible"
                reasons.append("Applicant is identified as an urban street vendor with vending operations.")
                reasons.append("Eligible to apply for collateral-free working capital loan (Tranche 1: ₹10k, Tranche 2: ₹20k, Tranche 3: ₹50k) with 7% interest subsidy.")
            else:
                eligibility = "not eligible"
                reasons.append("PM SVANidhi is strictly reserved for urban street vendors holding a Vending Certificate / CoV.")
                reasons.append("Commercial shops or retail establishments with permanent premises are not eligible.")

        elif s_id == "mudra_pmmy":
            if biz_type in ["RETAIL_KIRANA", "AGRI_TRADER", "MICRO_ENTERPRISE"]:
                eligibility = "may be eligible"
                reasons.append("Applicant operates a non-farm micro commercial enterprise.")
                reasons.append("Eligible under Shishu (up to ₹50k) or Kishore (₹50k–₹5L) categories.")
                reasons.append("Note: Final interest rate is set by individual lending banks/NBFCs based on commercial risk scoring.")
            else:
                eligibility = "not eligible"
                reasons.append("MUDRA loans are exclusively intended for non-farm income-generating commercial micro enterprises, not salaried personal credit.")

        elif s_id == "rbi_collateral_free_mse":
            if has_udyam and udyam_cat in ["MICRO", "SMALL"]:
                eligibility = "may be eligible"
                reasons.append(f"Holds an active Udyam Registration Certificate in the {udyam_cat.title()} category.")
                reasons.append("Scheduled Commercial Banks are mandated under RBI guidelines (effective April 1, 2026) not to accept collateral security for MSE loans up to ₹20 lakh.")
            else:
                eligibility = "not eligible"
                reasons.append("Requires a valid Udyam Registration Certificate and classification as a Micro or Small Enterprise (MSE).")

        elif s_id == "cgtmse":
            if has_udyam or biz_type in ["RETAIL_KIRANA", "AGRI_TRADER"]:
                eligibility = "may be eligible"
                reasons.append("Enterprise may qualify for lender credit guarantee cover (75%–85%) without providing third-party collateral.")
                reasons.append("Important Catch: CGTMSE guarantees the lending institution against default; it is NOT a direct cash subsidy or debt waiver for the borrower.")
            else:
                eligibility = "not eligible"
                reasons.append("CGTMSE coverage is restricted to micro and small business enterprises, not personal consumer loans.")

        elif s_id == "pmegp":
            if is_new_unit:
                eligibility = "may be eligible"
                reasons.append("Applicant is setting up a qualifying NEW micro-enterprise unit.")
                reasons.append("Eligible for 15% to 35% margin money subsidy via KVIC/DIC.")
            else:
                eligibility = "not eligible"
                reasons.append("PMEGP subsidy is strictly restricted to establishing NEW micro-enterprises.")
                reasons.append("Existing operational units, working capital expansion, or loan refinancing are strictly NOT eligible.")

        results.append({
            "id": s_id,
            "name": scheme.get("name"),
            "eligibility_verdict": eligibility,
            "who_it_is_for": scheme.get("who_it_is_for"),
            "what_it_gives": scheme.get("what_it_gives"),
            "catch": scheme.get("catch"),
            "reasons": reasons,
            "official_url": scheme.get("official_url"),
            "last_verified": scheme.get("last_verified")
        })

    return results


def calculate_refinance_comparison(
    existing_loan: Dict[str, Any],
    candidate_offer: Dict[str, Any],
    weekly_capacity: float
) -> Dict[str, Any]:
    """
    Deterministic refinance calculator.
    Compares existing loan vs candidate offer.
    Enforces 4 strict block conditions:
      1. New monthly EMI > capacity
      2. Total cost not lower (net savings <= 0)
      3. Hardship / sensitive event active
      4. New loan from the same lender to clear overdue amount (evergreening prevention)
    """
    # 1. Existing loan parameters
    outstanding = float(existing_loan.get("outstanding_principal_inr", 0.0))
    curr_emi = float(existing_loan.get("current_emi_inr", 0.0))
    rem_tenure = int(existing_loan.get("remaining_tenure_months", 1))
    prepayment_charge_pct = float(existing_loan.get("prepayment_charge_pct", 0.0))
    existing_lender_id = existing_loan.get("lender_id", "lender_unknown")
    is_overdue = bool(existing_loan.get("is_overdue", False))
    has_hardship = bool(existing_loan.get("has_hardship_flag", False))

    total_remaining_existing_cost = round(curr_emi * rem_tenure, 2)

    # 2. Candidate offer parameters
    new_apr = float(candidate_offer.get("interest_rate_apr", 18.0))
    new_tenure = int(candidate_offer.get("tenure_months", 12))
    proc_fee_pct = float(candidate_offer.get("processing_fee_pct", 1.5))
    candidate_lender_id = candidate_offer.get("lender_id", "new_lender")

    # Financial math for new loan
    prepayment_penalty_inr = round(outstanding * (prepayment_charge_pct / 100.0), 2)
    proc_fee_inr = round(outstanding * (proc_fee_pct / 100.0), 2)
    upfront_fees_total = round(prepayment_penalty_inr + proc_fee_inr, 2)

    # Monthly interest rate
    r = (new_apr / 100.0) / 12.0
    if r > 0 and new_tenure > 0:
        new_emi = outstanding * (r * ((1 + r) ** new_tenure)) / (((1 + r) ** new_tenure) - 1)
    else:
        new_emi = outstanding / new_tenure if new_tenure > 0 else outstanding
    new_emi = round(new_emi, 2)

    total_new_loan_repayment = round(new_emi * new_tenure, 2)
    total_new_cost = round(total_new_loan_repayment + upfront_fees_total, 2)

    net_savings_inr = round(total_remaining_existing_cost - total_new_cost, 2)
    monthly_emi_diff = round(curr_emi - new_emi, 2)

    # Break-even month calculation
    if monthly_emi_diff > 0 and upfront_fees_total > 0:
        break_even_month = round(upfront_fees_total / monthly_emi_diff, 1)
    elif monthly_emi_diff > 0 and upfront_fees_total == 0:
        break_even_month = 0.0
    else:
        break_even_month = None

    # Check 4 Hard Block Conditions
    blocks = []
    
    # Block 1: New EMI exceeds capacity
    monthly_capacity = round(weekly_capacity * 4.33, 2)
    if new_emi > monthly_capacity:
        blocks.append({
            "code": "BLOCK_EMI_EXCEEDS_CAPACITY",
            "reason": f"New monthly EMI (₹{new_emi:,.2f}) exceeds calculated safe capacity (₹{monthly_capacity:,.2f}/month). Refinancing would increase payment distress."
        })

    # Block 2: Total cost not lower
    if net_savings_inr <= 0:
        blocks.append({
            "code": "BLOCK_COST_NOT_LOWER",
            "reason": f"Total cost of new offer (₹{total_new_cost:,.2f}) is higher than existing remaining cost (₹{total_remaining_existing_cost:,.2f}) by ₹{-net_savings_inr:,.2f}. Extending tenure increases overall interest."
        })

    # Block 3: Hardship / sensitive event active
    if has_hardship:
        blocks.append({
            "code": "BLOCK_HARDSHIP_FLAG_ACTIVE",
            "reason": "Active sensitive-event or hardship condition flagged on account. New debt origination is prohibited during relief periods; route to human supervisor."
        })

    # Block 4: New loan from same lender to clear overdue debt (Evergreening prevention)
    if existing_lender_id == candidate_lender_id and is_overdue:
        blocks.append({
            "code": "BLOCK_EVERGREENING_SAME_LENDER",
            "reason": "Evergreening Prevention: Issuing a new loan from the same lender to settle an active overdue debt is prohibited by policy. Route to Human Credit Committee for structured restructuring."
        })

    is_blocked = len(blocks) > 0
    if is_blocked:
        verdict = f"REFINANCE BLOCKED ({len(blocks)} safety policy violation{'s' if len(blocks) > 1 else ''})"
    elif net_savings_inr > 0:
        verdict = f"AFFORDABLE REFINANCE VIABLE: Saves ₹{net_savings_inr:,.2f} total; break-even in {break_even_month} months."
    else:
        verdict = "REFINANCE NOT BENEFICIAL"

    return {
        "existing_loan": {
            "outstanding_principal_inr": outstanding,
            "current_emi_inr": curr_emi,
            "remaining_tenure_months": rem_tenure,
            "prepayment_charge_pct": prepayment_charge_pct,
            "total_remaining_cost_inr": total_remaining_existing_cost,
            "lender_id": existing_lender_id,
            "is_overdue": is_overdue,
            "has_hardship_flag": has_hardship
        },
        "candidate_offer": {
            "offer_id": candidate_offer.get("offer_id", "CUSTOM"),
            "product_name": candidate_offer.get("product_name", "Refinance Offer"),
            "lender_name": candidate_offer.get("lender_name", "Demo Lender"),
            "interest_rate_apr": new_apr,
            "tenure_months": new_tenure,
            "processing_fee_pct": proc_fee_pct,
            "new_monthly_emi_inr": new_emi,
            "upfront_fees_total_inr": upfront_fees_total,
            "total_new_cost_inr": total_new_cost
        },
        "comparison": {
            "net_savings_inr": net_savings_inr,
            "monthly_cashflow_savings_inr": monthly_emi_diff,
            "break_even_month": break_even_month,
            "monthly_capacity_inr": monthly_capacity,
            "is_blocked": is_blocked,
            "block_reasons": blocks,
            "verdict": verdict
        }
    }


def generate_advisor_observations(
    inflow_pattern: Dict[str, Any],
    categories_summary: Dict[str, Any],
    capacity_plan: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Generates data-grounded observations for a human advisor (no ROI promises).
    Shown as 'questions to discuss' with a handoff button.
    """
    observations = []

    # 1. Weekend vs Weekday Inflow Share
    weekend_share = inflow_pattern.get("weekend_share_pct", 0.0)
    peak_day = inflow_pattern.get("peak_day", "Weekend")
    if weekend_share > 35.0:
        observations.append({
            "topic": "Cash Inflow Timing & Mandate Day Alignment",
            "observation": f"Weekend cash receipts account for {weekend_share}% of total weekly collections, peaking on {peak_day}.",
            "question_to_discuss": f"Could recurring repayment mandates be aligned to {peak_day} evening or Monday morning instead of mid-week to match peak customer liquidity?"
        })

    # 2. Supplier / Stock Outflow Concentration
    stock_spend = categories_summary.get("stock_supplier", {}).get("total_inr", 0.0)
    total_debits = sum(c.get("total_inr", 0.0) for c in categories_summary.values())
    if total_debits > 0 and (stock_spend / total_debits) > 0.40:
        stock_share = round((stock_spend / total_debits) * 100, 1)
        observations.append({
            "topic": "Supplier Inventory Cycle Synchronization",
            "observation": f"Wholesale supplier and stock purchases comprise {stock_share}% of total operational outflows, creating concentrated weekly outflows.",
            "question_to_discuss": "Could supplier payment terms be staggered into bi-weekly cycles to avoid deep mid-week cash deficits?"
        })

    # 3. Cashflow Volatility & Buffer Absorption
    cv = inflow_pattern.get("volatility_cv", 0.0)
    worst_week = inflow_pattern.get("worst_week", {})
    best_week = inflow_pattern.get("best_week", {})
    if cv > 0.30:
        observations.append({
            "topic": "Seasonal & Cyclical Buffer Cushioning",
            "observation": f"Weekly cashflow exhibits high variation (CV {cv}), swinging between ₹{worst_week.get('inflow_inr', 0):,.0f} (Week {worst_week.get('week_number')}) and ₹{best_week.get('inflow_inr', 0):,.0f} (Week {best_week.get('week_number')}).",
            "question_to_discuss": "Should a flexible micro-split schedule be instituted during low-sales periods to prevent mandate bounce events?"
        })

    # 4. Debt Servicing Capacity Headroom
    cap_val = capacity_plan.get("final_weekly_capacity_inr", 0.0)
    if cap_val <= 500.0:
        observations.append({
            "topic": "Restructuring & Tenor Extension Review",
            "observation": f"Calculated safe-to-pay capacity is constrained at ₹{cap_val:,.2f}/week after accounting for basic operational essentials.",
            "question_to_discuss": "Does the borrower require an extended tenor restructuring or temporary interest-only moratoria to stabilize working capital?"
        })

    return observations


def run_full_cashflow_coach(
    persona_id: str,
    custom_role_overrides: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Main orchestrator for Cash-Flow Coach.
    Consent-gated: Returns consent_required if consent is not ACTIVE.
    """
    consent_info = get_consent(persona_id)
    if not consent_info.get("granted") or consent_info.get("status") != "ACTIVE":
        return {
            "consent_required": True,
            "persona_id": persona_id,
            "consent_info": consent_info,
            "message": "Consent required to view cash-flow check-up. The borrower must grant consent first."
        }

    raw = get_persona_raw_data(persona_id)
    if not raw:
        return {"error": f"Persona '{persona_id}' not found"}

    policy = load_coach_policy()
    taxonomy = policy.get("taxonomy", {})
    buffer_pct = float(policy.get("buffer_pct", 0.15))
    min_capacity_per_week = float(policy.get("min_capacity_per_week_inr", 500.0))
    max_capacity_share = float(policy.get("max_capacity_share_of_inflow", 0.40))

    transactions = raw.get("transactions", [])
    attributes = raw.get("attributes", {})

    # 1. Categorise Transactions
    classified_txns = []
    category_totals: Dict[str, Dict[str, Any]] = {}
    
    # Combine policy roles with user custom overrides
    user_overrides = custom_role_overrides or CATEGORY_OVERRIDES.get(persona_id, {})

    for txn in transactions:
        t_type = txn.get("type", "DEBIT")
        amt = float(txn.get("amount", 0.0))
        narration = txn.get("narration", "")

        if t_type == "CREDIT":
            classified_txns.append({
                **txn,
                "category": "income_credit",
                "display_name": "Inflow Credit",
                "role": "inflow"
            })
        else:
            cls = classify_transaction(narration, taxonomy)
            cat_id = cls["category"]
            
            # Apply user role override if present
            role = user_overrides.get(cat_id, cls["role"])

            if cat_id not in category_totals:
                category_totals[cat_id] = {
                    "category": cat_id,
                    "display_name": cls["display_name"],
                    "role": role,
                    "total_inr": 0.0,
                    "txn_count": 0,
                    "is_essential": (role == "essential")
                }
            category_totals[cat_id]["total_inr"] += amt
            category_totals[cat_id]["txn_count"] += 1

            classified_txns.append({
                **txn,
                "category": cat_id,
                "display_name": cls["display_name"],
                "role": role,
                "confidence": cls["confidence"],
                "method": cls["method"]
            })

    # Round totals
    for cat_id, d in category_totals.items():
        d["total_inr"] = round(d["total_inr"], 2)
        d["monthly_avg_inr"] = round(d["total_inr"] / 3.0, 2)

    # 2. Inflow Pattern
    inflow_pattern = analyze_inflow_pattern(transactions)

    # 3. Safe-to-Pay Capacity
    weeks_count = max(1, inflow_pattern.get("weeks_count", 13))
    essential_outflow_total = sum(d["total_inr"] for d in category_totals.values() if d["role"] == "essential")
    avg_weekly_essential_outflow = round(essential_outflow_total / weeks_count, 2)
    worst_quartile_inflow = inflow_pattern.get("worst_quartile_weekly_inflow", 0.0)

    capacity_plan = compute_safe_to_pay_capacity(
        worst_quartile_weekly_inflow=worst_quartile_inflow,
        average_weekly_essential_outflow=avg_weekly_essential_outflow,
        buffer_pct=buffer_pct,
        min_capacity_per_week_inr=min_capacity_per_week,
        max_capacity_share_of_inflow=max_capacity_share
    )

    # 4. Public Schemes Matching
    schemes_doc = load_schemes_policy()
    matched_schemes = match_government_schemes(attributes, schemes_doc.get("schemes", []))

    # 5. Pre-Approved Refinance Options
    preapproved_offers = load_preapproved_offers()
    weekly_cap = capacity_plan.get("final_weekly_capacity_inr", 0.0)
    existing_loan = attributes.get("existing_loan", {})
    
    refinance_results = []
    for offer in preapproved_offers:
        target_personas = offer.get("target_personas", [])
        if not target_personas or persona_id in target_personas:
            comparison = calculate_refinance_comparison(existing_loan, offer, weekly_cap)
            refinance_results.append(comparison)

    # 6. Advisor Observations
    advisor_obs = generate_advisor_observations(inflow_pattern, category_totals, capacity_plan)

    return {
        "consent_required": False,
        "persona_id": persona_id,
        "name": raw.get("name"),
        "account_type": raw.get("account_type"),
        "bank_name": raw.get("bank_name"),
        "masked_account": raw.get("masked_account"),
        "consent_info": consent_info,
        "inflow_pattern": inflow_pattern,
        "categories_summary": category_totals,
        "capacity_plan": capacity_plan,
        "matched_schemes": matched_schemes,
        "schemes_disclaimer": schemes_doc.get("disclaimer", "Verify with the lender or official portal before applying."),
        "refinance_options": refinance_results,
        "advisor_observations": advisor_obs,
        "footer_disclaimer": "Information, not financial advice.",
        "label": raw.get("label", "synthetic data; production uses RBI Account Aggregator consent via the lender")
    }
