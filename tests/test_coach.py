import pytest
import os
import json
from services.coach import (
    record_consent,
    get_consent,
    run_full_cashflow_coach,
    compute_safe_to_pay_capacity,
    match_government_schemes,
    calculate_refinance_comparison,
    load_coach_policy,
    load_schemes_policy,
    load_preapproved_offers,
    get_available_personas
)

def test_available_personas():
    personas = get_available_personas()
    assert len(personas) >= 3
    ids = [p["persona_id"] for p in personas]
    assert "kirana_owner" in ids
    assert "salaried_household" in ids
    assert "agri_trader" in ids

def test_consent_gating():
    persona_id = "test_consent_kirana"
    
    # 1. Unconsented initially -> blocked
    res = run_full_cashflow_coach(persona_id)
    assert res.get("consent_required") is True
    assert "Consent required" in res.get("message", "")

    # 2. Grant Consent -> active
    consent_rec = record_consent(persona_id, granted=True, purpose="AFFORDABLE_REPAYMENT_ASSESSMENT")
    assert consent_rec["granted"] is True
    assert consent_rec["status"] == "ACTIVE"
    assert consent_rec["consent_id"].startswith("AA-CONSENT-")
    
    # 3. Revoke Consent -> blocked again
    revoked_rec = record_consent(persona_id, granted=False)
    assert revoked_rec["granted"] is False
    assert revoked_rec["status"] == "REVOKED"
    
    res_after_revoke = run_full_cashflow_coach(persona_id)
    assert res_after_revoke.get("consent_required") is True

def test_capacity_math_and_buffer():
    # Deterministic test values
    worst_q_inflow = 20000.0
    essential_outflow = 12000.0
    buffer_pct = 0.15
    
    # Buffer = 20,000 * 0.15 = 3,000
    # Raw capacity = 20,000 - 12,000 - 3,000 = 5,000
    cap = compute_safe_to_pay_capacity(
        worst_quartile_weekly_inflow=worst_q_inflow,
        average_weekly_essential_outflow=essential_outflow,
        buffer_pct=buffer_pct,
        min_capacity_per_week_inr=500.0,
        max_capacity_share_of_inflow=0.40
    )
    assert cap["safety_buffer_inr"] == 3000.0
    assert cap["raw_capacity_inr"] == 5000.0
    assert cap["final_weekly_capacity_inr"] == 5000.0
    assert cap["is_viable"] is True

    # If essentials exceed inflow -> zero capacity
    cap_zero = compute_safe_to_pay_capacity(
        worst_quartile_weekly_inflow=10000.0,
        average_weekly_essential_outflow=11000.0,
        buffer_pct=0.15
    )
    assert cap_zero["final_weekly_capacity_inr"] == 0.0
    assert cap_zero["is_viable"] is False

def test_category_flexibility_recalculation():
    # When user marks a category flexible, capacity increases
    record_consent("kirana_owner", granted=True)
    res_default = run_full_cashflow_coach("kirana_owner")
    assert res_default["consent_required"] is False
    default_cap = res_default["capacity_plan"]["final_weekly_capacity_inr"]

    # Now override 'household_essentials' or 'wages' to flexible
    res_flexible = run_full_cashflow_coach("kirana_owner", custom_role_overrides={"wages": "flexible"})
    flex_cap = res_flexible["capacity_plan"]["final_weekly_capacity_inr"]
    # Less essential outflows -> higher capacity
    assert flex_cap >= default_cap

def test_government_schemes_eligibility():
    schemes_doc = load_schemes_policy()
    schemes = schemes_doc["schemes"]

    # 1. Kirana Owner attributes (non-vendor, existing enterprise, has Udyam)
    kirana_attrs = {
        "business_type": "RETAIL_KIRANA",
        "is_street_vendor": False,
        "is_new_enterprise": False,
        "has_udyam_registration": True,
        "udyam_category": "MICRO"
    }
    matches = {m["id"]: m for m in match_government_schemes(kirana_attrs, schemes)}
    
    # SVANidhi: Must be not eligible because kirana is not a street vendor
    assert matches["pm_svanidhi"]["eligibility_verdict"] == "not eligible"
    assert any("street vendor" in r.lower() for r in matches["pm_svanidhi"]["reasons"])

    # PMEGP: Must be not eligible because kirana is an existing enterprise
    assert matches["pmegp"]["eligibility_verdict"] == "not eligible"
    assert any("new enterprise" in r.lower() or "existing" in r.lower() for r in matches["pmegp"]["reasons"])

    # MUDRA: May be eligible with rate disclaimer
    assert matches["mudra_pmmy"]["eligibility_verdict"] == "may be eligible"
    assert any("lender" in r.lower() or "risk" in r.lower() for r in matches["mudra_pmmy"]["reasons"])

    # RBI Collateral-Free MSE: May be eligible (has Udyam Micro)
    assert matches["rbi_collateral_free_mse"]["eligibility_verdict"] == "may be eligible"

    # CGTMSE: May be eligible (guarantee cover, not cash subsidy)
    assert matches["cgtmse"]["eligibility_verdict"] == "may be eligible"
    assert any("guarantee" in r.lower() for r in matches["cgtmse"]["reasons"])

    # 2. Street vendor test case
    street_vendor_attrs = {
        "business_type": "STREET_VENDOR",
        "is_street_vendor": True,
        "is_new_enterprise": False,
        "has_udyam_registration": False
    }
    sv_matches = {m["id"]: m for m in match_government_schemes(street_vendor_attrs, schemes)}
    assert sv_matches["pm_svanidhi"]["eligibility_verdict"] == "may be eligible"

    # 3. New Enterprise test case
    new_unit_attrs = {
        "business_type": "MANUFACTURING",
        "is_street_vendor": False,
        "is_new_enterprise": True,
        "has_udyam_registration": True,
        "udyam_category": "MICRO"
    }
    new_matches = {m["id"]: m for m in match_government_schemes(new_unit_attrs, schemes)}
    assert new_matches["pmegp"]["eligibility_verdict"] == "may be eligible"

def test_refinance_block_conditions():
    # Base existing loan
    existing_loan = {
        "outstanding_principal_inr": 40000.0,
        "current_emi_inr": 5460.0,
        "remaining_tenure_months": 8,
        "prepayment_charge_pct": 2.0,
        "lender_id": "demo_lender_a",
        "is_overdue": True,
        "has_hardship_flag": False
    }

    weekly_cap = 2000.0 # ~₹8,660/month

    # Condition 1: New EMI > Capacity -> BLOCKED
    high_emi_offer = {
        "offer_id": "HIGH_EMI",
        "lender_id": "demo_lender_b",
        "interest_rate_apr": 16.0,
        "tenure_months": 3, # Very short tenure -> EMI will be ~₹13,600 > ₹8,660 capacity
        "processing_fee_pct": 1.0
    }
    comp1 = calculate_refinance_comparison(existing_loan, high_emi_offer, weekly_capacity=weekly_cap)
    assert comp1["comparison"]["is_blocked"] is True
    codes = [b["code"] for b in comp1["comparison"]["block_reasons"]]
    assert "BLOCK_EMI_EXCEEDS_CAPACITY" in codes

    # Condition 2: Total cost not lower -> BLOCKED
    expensive_offer = {
        "offer_id": "EXPENSIVE_TENURE",
        "lender_id": "demo_lender_b",
        "interest_rate_apr": 26.0,
        "tenure_months": 36, # Long tenure with high interest -> higher total cost
        "processing_fee_pct": 3.0
    }
    comp2 = calculate_refinance_comparison(existing_loan, expensive_offer, weekly_capacity=weekly_cap)
    assert comp2["comparison"]["is_blocked"] is True
    codes = [b["code"] for b in comp2["comparison"]["block_reasons"]]
    assert "BLOCK_COST_NOT_LOWER" in codes

    # Condition 3: Hardship / sensitive event active -> BLOCKED
    hardship_loan = {**existing_loan, "has_hardship_flag": True}
    good_offer = {
        "offer_id": "GOOD_OFFER",
        "lender_id": "demo_lender_b",
        "interest_rate_apr": 15.0,
        "tenure_months": 10,
        "processing_fee_pct": 1.0
    }
    comp3 = calculate_refinance_comparison(hardship_loan, good_offer, weekly_capacity=weekly_cap)
    assert comp3["comparison"]["is_blocked"] is True
    codes = [b["code"] for b in comp3["comparison"]["block_reasons"]]
    assert "BLOCK_HARDSHIP_FLAG_ACTIVE" in codes

    # Condition 4: New loan from same lender to clear overdue -> BLOCKED (Evergreening)
    same_lender_offer = {
        "offer_id": "SAME_LENDER",
        "lender_id": "demo_lender_a", # Same as existing_loan['lender_id']
        "interest_rate_apr": 15.0,
        "tenure_months": 10,
        "processing_fee_pct": 1.0
    }
    comp4 = calculate_refinance_comparison(existing_loan, same_lender_offer, weekly_capacity=weekly_cap)
    assert comp4["comparison"]["is_blocked"] is True
    codes = [b["code"] for b in comp4["comparison"]["block_reasons"]]
    assert "BLOCK_EVERGREENING_SAME_LENDER" in codes

    # Valid Offer from different lender when not overdue / lower cost
    not_overdue_loan = {**existing_loan, "is_overdue": False, "remaining_tenure_months": 10, "current_emi_inr": 5460.0}
    comp_valid = calculate_refinance_comparison(not_overdue_loan, good_offer, weekly_capacity=weekly_cap)
    assert comp_valid["comparison"]["is_blocked"] is False
    assert comp_valid["comparison"]["net_savings_inr"] > 0
    assert comp_valid["comparison"]["break_even_month"] is not None

def test_advisor_observations():
    record_consent("kirana_owner", granted=True)
    res = run_full_cashflow_coach("kirana_owner")
    obs = res.get("advisor_observations", [])
    assert len(obs) >= 2
    # Verify presence of questions to discuss
    for o in obs:
        assert "question_to_discuss" in o
        assert "observation" in o
        # No ROI promises
        assert "guaranteed" not in o["observation"].lower()
        assert "roi" not in o["observation"].lower()

def test_coach_api_endpoints():
    from starlette.testclient import TestClient
    from app.main import app
    client = TestClient(app)

    # 1. Personas endpoint
    res = client.get("/api/coach/personas")
    assert res.status_code == 200
    personas = res.json()["personas"]
    assert len(personas) >= 3

    # 2. Consent check (unconsented)
    client.post("/api/coach/consent", json={"persona_id": "api_test_user", "granted": False})
    res = client.get("/api/coach/analysis?persona_id=api_test_user")
    assert res.status_code == 200
    assert res.json()["consent_required"] is True

    # 3. Grant Consent via API
    res = client.post("/api/coach/consent", json={
        "persona_id": "kirana_owner",
        "granted": True,
        "purpose": "AFFORDABLE_REPAYMENT_ASSESSMENT"
    })
    assert res.status_code == 200
    assert res.json()["status"] == "ACTIVE"

    # 4. Analysis via API
    res = client.get("/api/coach/analysis?persona_id=kirana_owner")
    assert res.status_code == 200
    data = res.json()
    assert data["consent_required"] is False
    assert "capacity_plan" in data
    assert data["capacity_plan"]["final_weekly_capacity_inr"] > 0
    assert len(data["matched_schemes"]) >= 5

    # 5. Category override
    res = client.post("/api/coach/override-category", json={
        "persona_id": "kirana_owner",
        "category": "wages",
        "role": "flexible"
    })
    assert res.status_code == 200
    assert res.json()["categories_summary"]["wages"]["role"] == "flexible"

    # 6. Advisor Handoff
    res = client.post("/api/coach/advisor-handoff", json={
        "persona_id": "kirana_owner",
        "notes": "Borrower interested in weekend-aligned mandate schedule."
    })
    assert res.status_code == 200
    ticket = res.json()
    assert "ticket_id" in ticket
    assert ticket["status"] == "QUEUED_FOR_HUMAN_CREDIT_ADVISOR"

