import json
import random
from datetime import datetime, timedelta

def generate_samples():
    random.seed(42)
    end_date = datetime(2026, 11, 19)
    start_date = end_date - timedelta(days=90)

    # 1. KIRANA OWNER (Sunita Patil - Shree Ganesh Kirana)
    kirana_txns = []
    curr = start_date
    txn_seq = 1000

    while curr <= end_date:
        d_str = curr.strftime("%Y-%m-%d")
        weekday = curr.weekday() # 0=Mon, 5=Sat, 6=Sun

        # Daily customer UPI inflows (2-4 transactions per day, higher on weekend)
        num_sales = random.randint(3, 5) if weekday in [4, 5, 6] else random.randint(2, 3)
        daily_inflow = random.uniform(3200, 6800) if weekday in [4, 5, 6] else random.uniform(1800, 3900)
        
        # Split daily inflow into 2-3 QR settlements
        part1 = round(daily_inflow * 0.6, 2)
        part2 = round(daily_inflow * 0.4, 2)
        txn_seq += 1
        kirana_txns.append({
            "txn_id": f"TXN-AA-{txn_seq}",
            "date": d_str,
            "amount": part1,
            "type": "CREDIT",
            "mode": "UPI",
            "narration": "UPI-SETTLE-PAYTM-QR-RETAIL-CREDIT"
        })
        txn_seq += 1
        kirana_txns.append({
            "txn_id": f"TXN-AA-{txn_seq}",
            "date": d_str,
            "amount": part2,
            "type": "CREDIT",
            "mode": "UPI",
            "narration": "UPI-SETTLE-PHONEPE-MERCHANT-INFLOW"
        })

        # Tuesday / Wednesday Stock purchases (weekly)
        if weekday == 1: # Tuesday
            stock_amt = round(random.uniform(9500, 16500), 2)
            txn_seq += 1
            supplier = random.choice([
                "METRO-CASH-CARRY-SUPPLIER-PAYMENT",
                "HINDUSTAN-UNILEVER-DISTRIBUTOR-DEBIT",
                "ITC-LIMITED-WHOLESALE-STOCK-ORDER",
                "AMUL-DAIRY-PRODUCTS-WHOLESALE-DEBIT"
            ])
            kirana_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": stock_amt,
                "type": "DEBIT",
                "mode": "NEFT",
                "narration": supplier
            })

        # Monthly shop rent (5th of month)
        if curr.day == 5:
            txn_seq += 1
            kirana_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": 11000.0,
                "type": "DEBIT",
                "mode": "IMPS",
                "narration": "RENT-TRANSFER-SHARMA-COMMERCIAL-SHOP"
            })

        # Monthly electricity / utilities (10th of month)
        if curr.day == 10:
            txn_seq += 1
            kirana_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": 2350.0,
                "type": "DEBIT",
                "mode": "BBPS",
                "narration": "MSEDCL-ELECTRICITY-BILL-COMMERCIAL"
            })

        # Monthly shop assistant wage (7th of month)
        if curr.day == 7:
            txn_seq += 1
            kirana_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": 8000.0,
                "type": "DEBIT",
                "mode": "UPI",
                "narration": "WAGES-SHOP-ASSISTANT-RAMESH"
            })

        # Existing loan EMI debit (3rd of month)
        if curr.day == 3:
            txn_seq += 1
            kirana_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": 5460.0,
                "type": "DEBIT",
                "mode": "NACH",
                "narration": "DEMO-LENDER-A-LOAN-EMI-DEBIT"
            })

        # Household essentials (Fridays)
        if weekday == 4:
            txn_seq += 1
            kirana_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": round(random.uniform(1200, 2400), 2),
                "type": "DEBIT",
                "mode": "UPI",
                "narration": "HOUSEHOLD-GROCERIES-MEDICINES-APOLLO"
            })

        # Occasional flexible spend
        if weekday == 6 and random.random() < 0.4:
            txn_seq += 1
            kirana_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": round(random.uniform(400, 950), 2),
                "type": "DEBIT",
                "mode": "UPI",
                "narration": "FAMILY-RESTAURANT-WEEKEND-OUTING"
            })

        curr += timedelta(days=1)

    kirana_data = {
        "persona_id": "kirana_owner",
        "name": "Sunita Patil (Shree Ganesh Kirana)",
        "account_type": "CURRENT",
        "bank_name": "Demo Bank Ltd.",
        "masked_account": "XXXXXX4091",
        "period_days": 90,
        "label": "synthetic data; production uses RBI Account Aggregator consent via the lender",
        "attributes": {
            "business_type": "RETAIL_KIRANA",
            "is_street_vendor": False,
            "is_new_enterprise": False,
            "enterprise_age_years": 4.5,
            "has_udyam_registration": True,
            "udyam_category": "MICRO",
            "annual_turnover_inr": 2400000.0,
            "existing_loan": {
                "lender_name": "Demo Lender A",
                "lender_id": "demo_lender_a",
                "loan_id": "LN-KIRANA-4091",
                "outstanding_principal_inr": 40000.0,
                "interest_rate_apr": 24.0,
                "remaining_tenure_months": 8,
                "current_emi_inr": 5460.0,
                "prepayment_charge_pct": 2.0,
                "is_overdue": True,
                "overdue_amount_inr": 10920.0,
                "dpd": 18,
                "has_hardship_flag": False
            }
        },
        "transactions": kirana_txns
    }

    with open("C:/Users/vajja/saarthi/data/aa_samples/kirana_owner.json", "w", encoding="utf-8") as f:
        json.dump(kirana_data, f, indent=2)

    # 2. SALARIED HOUSEHOLD (Rajesh Sharma)
    salary_txns = []
    curr = start_date
    while curr <= end_date:
        d_str = curr.strftime("%Y-%m-%d")
        weekday = curr.weekday()

        # Monthly Salary Credit on 1st
        if curr.day == 1:
            txn_seq += 1
            salary_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": 62500.0,
                "type": "CREDIT",
                "mode": "NEFT",
                "narration": "SALARY-CREDIT-TECH-INNOVATIONS-LTD"
            })

        # House rent on 3rd
        if curr.day == 3:
            txn_seq += 1
            salary_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": 16500.0,
                "type": "DEBIT",
                "mode": "IMPS",
                "narration": "HOUSE-RENT-TRANSFER-LANDLORD"
            })

        # Existing Loan EMI on 5th
        if curr.day == 5:
            txn_seq += 1
            salary_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": 9580.0,
                "type": "DEBIT",
                "mode": "NACH",
                "narration": "DEMO-LENDER-A-PERSONAL-LOAN-EMI"
            })

        # Utilities on 8th
        if curr.day == 8:
            txn_seq += 1
            salary_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": 3100.0,
                "type": "DEBIT",
                "mode": "BBPS",
                "narration": "ELECTRICITY-WIFI-GAS-BILL-PAYMENT"
            })

        # Weekly Groceries on Saturdays
        if weekday == 5:
            txn_seq += 1
            salary_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": round(random.uniform(2200, 3400), 2),
                "type": "DEBIT",
                "mode": "UPI",
                "narration": "SUPERMARKET-WEEKLY-GROCERIES-RETAIL"
            })

        # Flexible Weekend Spends
        if weekday in [5, 6] and random.random() < 0.6:
            txn_seq += 1
            salary_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": round(random.uniform(550, 1600), 2),
                "type": "DEBIT",
                "mode": "UPI",
                "narration": random.choice(["SWIGGY-ONLINE-FOOD-ORDER", "ZOMATO-DINING-OUT", "AMAZON-RETAIL-SHOPPING", "BOOKMYSHOW-ENTERTAINMENT"])
            })

        # Daily transit on weekdays
        if weekday in [0, 1, 2, 3, 4] and random.random() < 0.5:
            txn_seq += 1
            salary_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": round(random.uniform(120, 280), 2),
                "type": "DEBIT",
                "mode": "UPI",
                "narration": "METRO-SMART-CARD-RECHARGE-TRANSPORT"
            })

        curr += timedelta(days=1)

    salaried_data = {
        "persona_id": "salaried_household",
        "name": "Rajesh Sharma",
        "account_type": "SAVINGS",
        "bank_name": "Demo Bank Ltd.",
        "masked_account": "XXXXXX8812",
        "period_days": 90,
        "label": "synthetic data; production uses RBI Account Aggregator consent via the lender",
        "attributes": {
            "business_type": "SALARIED",
            "is_street_vendor": False,
            "is_new_enterprise": False,
            "has_udyam_registration": False,
            "existing_loan": {
                "lender_name": "Demo Lender A",
                "lender_id": "demo_lender_a",
                "loan_id": "LN-SALARY-1102",
                "outstanding_principal_inr": 150000.0,
                "interest_rate_apr": 18.0,
                "remaining_tenure_months": 18,
                "current_emi_inr": 9580.0,
                "prepayment_charge_pct": 3.0,
                "is_overdue": False,
                "dpd": 0,
                "has_hardship_flag": False
            }
        },
        "transactions": salary_txns
    }

    with open("C:/Users/vajja/saarthi/data/aa_samples/salaried_household.json", "w", encoding="utf-8") as f:
        json.dump(salaried_data, f, indent=2)

    # 3. AGRI TRADER (Manjunath Gowda)
    agri_txns = []
    curr = start_date
    mandi_cycle_day = 0

    while curr <= end_date:
        d_str = curr.strftime("%Y-%m-%d")
        weekday = curr.weekday()
        mandi_cycle_day += 1

        # Mandi bulk credits every 14-18 days
        if mandi_cycle_day in [10, 25, 42, 60, 78]:
            txn_seq += 1
            agri_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": round(random.uniform(75000, 125000), 2),
                "type": "CREDIT",
                "mode": "RTGS",
                "narration": "APMC-GRAIN-MANDI-PRODUCE-AUCTION-CREDIT"
            })

        # Input supplies / Fertilizer & Seeds
        if mandi_cycle_day in [12, 28, 45, 63, 80]:
            txn_seq += 1
            agri_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": round(random.uniform(32000, 58000), 2),
                "type": "DEBIT",
                "mode": "NEFT",
                "narration": "AGRI-FERTILIZER-SEEDS-DEPOT-SUPPLIER"
            })

        # Mandi cess and transport logistics
        if weekday == 3:
            txn_seq += 1
            agri_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": round(random.uniform(4500, 8500), 2),
                "type": "DEBIT",
                "mode": "IMPS",
                "narration": "FREIGHT-TRANSPORT-TRACTOR-LOGISTICS-DIESEL"
            })

        # Warehouse / Cold storage rental
        if curr.day == 12:
            txn_seq += 1
            agri_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": 14000.0,
                "type": "DEBIT",
                "mode": "NEFT",
                "narration": "WAREHOUSE-COLD-STORAGE-RENT-PAYMENT"
            })

        # Monthly loan EMI
        if curr.day == 4:
            txn_seq += 1
            agri_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": 8800.0,
                "type": "DEBIT",
                "mode": "NACH",
                "narration": "DEMO-LENDER-B-AGRI-COMMERCIAL-LOAN-EMI"
            })

        # Household essentials
        if weekday == 6:
            txn_seq += 1
            agri_txns.append({
                "txn_id": f"TXN-AA-{txn_seq}",
                "date": d_str,
                "amount": round(random.uniform(1800, 3200), 2),
                "type": "DEBIT",
                "mode": "UPI",
                "narration": "RURAL-ESSENTIALS-MEDICINES-GROCERIES"
            })

        curr += timedelta(days=1)

    agri_data = {
        "persona_id": "agri_trader",
        "name": "Manjunath Gowda (Kaveri Agri Trading)",
        "account_type": "CURRENT",
        "bank_name": "Demo Bank Ltd.",
        "masked_account": "XXXXXX6643",
        "period_days": 90,
        "label": "synthetic data; production uses RBI Account Aggregator consent via the lender",
        "attributes": {
            "business_type": "AGRI_TRADER",
            "is_street_vendor": False,
            "is_new_enterprise": False,
            "enterprise_age_years": 6.0,
            "has_udyam_registration": True,
            "udyam_category": "SMALL",
            "annual_turnover_inr": 6200000.0,
            "existing_loan": {
                "lender_name": "Demo Lender B",
                "lender_id": "demo_lender_b",
                "loan_id": "LN-AGRI-8821",
                "outstanding_principal_inr": 80000.0,
                "interest_rate_apr": 21.0,
                "remaining_tenure_months": 10,
                "current_emi_inr": 8800.0,
                "prepayment_charge_pct": 2.5,
                "is_overdue": False,
                "overdue_amount_inr": 0.0,
                "dpd": 0,
                "has_hardship_flag": True  # crop yield delay hardship active
            }
        },
        "transactions": agri_txns
    }

    with open("C:/Users/vajja/saarthi/data/aa_samples/agri_trader.json", "w", encoding="utf-8") as f:
        json.dump(agri_data, f, indent=2)

    print("Generated 3 synthetic AA sample datasets in data/aa_samples/")

if __name__ == "__main__":
    generate_samples()
