import urllib.request
import json
import pytest

BASE = "http://127.0.0.1:8000"

def test_full_system_e2e():
    # Reset book first
    req = urllib.request.Request(f"{BASE}/api/load-sample-book?workflow_id=collections", method="POST")
    urllib.request.urlopen(req)

    # 1. S1 Hero Test (Sunita Patil)
    req = urllib.request.Request(f"{BASE}/api/events/scenario/s1", method="POST")
    s1 = json.loads(urllib.request.urlopen(req).read())
    assert s1["status"] == "ptp"
    assert "repayments.saarthi@yesbank" in s1["payment_link"]
    print("[PASS] S1 Hero:", s1["customer_name"], s1["status"], s1["payment_link"][:45])

    # S1 Simulate Payment -> Flips to PAID
    req = urllib.request.Request(f"{BASE}/api/cases/1/simulate-payment", method="POST")
    s1_paid = json.loads(urllib.request.urlopen(req).read())
    assert s1_paid["status"] == "paid"
    print("[PASS] S1 Simulate Pay -> Status is now PAID")

    # 2. S2 Part Payment (Rajesh Sharma)
    req = urllib.request.Request(f"{BASE}/api/events/scenario/s2", method="POST")
    s2 = json.loads(urllib.request.urlopen(req).read())
    assert s2["status"] == "ptp"
    assert s2["data"]["policy_firewall"]["rule_id"] == "POLICY-PART-MIN01"
    print("[PASS] S2 Part-Pay:", s2["customer_name"], s2["data"]["policy_firewall"]["rule_id"])

    # 3. S3 Adversarial Waiver Block (Vikram Malhotra)
    req = urllib.request.Request(f"{BASE}/api/events/scenario/s3", method="POST")
    s3 = json.loads(urllib.request.urlopen(req).read())
    assert s3["status"] == "escalated"
    assert s3["data"]["policy_firewall"]["status"] == "BLOCKED"
    assert s3["data"]["policy_firewall"]["rule_id"] == "POLICY-WAIVER-NO01"
    assert s3["payment_link"] is None
    print("[PASS] S3 Adversarial Block:", s3["customer_name"], s3["data"]["policy_firewall"]["rule_id"], "Zero Link")

    # 4. S4 Hospital Sensitive Pause (Suresh Patil)
    req = urllib.request.Request(f"{BASE}/api/events/scenario/s4", method="POST")
    s4 = json.loads(urllib.request.urlopen(req).read())
    assert s4["status"] == "escalated"
    assert s4["data"]["policy_firewall"]["status"] == "SENSITIVE_PAUSE"
    assert s4["data"]["policy_firewall"]["rule_id"] == "FAIR-PRAC-SENS01"
    assert s4["do_not_contact_until"] is not None
    hc = s4.get("hospicash_claim") or s4["data"].get("hospicash_claim")
    assert hc is not None
    assert hc["policy_number"] == "HC-99281-PN"
    assert hc["max_relief_amount_inr"] == 15000.0
    print("[PASS] S4 Sensitive Pause + Hospicash Claim:", s4["customer_name"], hc["policy_number"], "₹15,000 relief")

    # 4b. S7 T-24h Preventive Rescue (Anjali Deshmukh)
    req = urllib.request.Request(f"{BASE}/api/events/scenario/s7", method="POST")
    s7 = json.loads(urllib.request.urlopen(req).read())
    assert s7["status"] == "ptp"
    assert s7["data"]["policy_firewall"]["rule_id"] == "POLICY-PREV-FEE01"
    assert s7.get("bounce_fee_saved_inr") == 590.0 or s7["data"].get("bounce_fee_saved_inr") == 590.0
    print("[PASS] S7 T-24h Rescue:", s7["customer_name"], "Saved ₹590 bounce fee, CIBIL safe")

    # 4c. S8 Kirana Cashflow 4x Micro-Split (Sunita Patil)
    req = urllib.request.Request(f"{BASE}/api/events/scenario/s8", method="POST")
    s8 = json.loads(urllib.request.urlopen(req).read())
    assert s8["status"] == "ptp"
    assert s8["data"]["policy_firewall"]["rule_id"] == "POLICY-MICRO-SPLIT01"
    micro = s8.get("micro_schedule") or s8["data"].get("micro_schedule")
    assert len(micro) == 4
    assert micro[0]["amount_inr"] == 10000.0
    assert micro[0]["rail"] == "UPI_NOW"
    assert micro[1]["rail"] == "UPI_AUTOPAY"
    print("[PASS] S8 Micro-Split:", s8["customer_name"], "4 Friday Tranches of ₹10,000 AutoPay")

    # 5. S5 Bad Transcript Threat (Manoj Kumar)
    req = urllib.request.Request(f"{BASE}/api/events/scenario/s5", method="POST")
    s5 = json.loads(urllib.request.urlopen(req).read())
    assert s5["status"] == "escalated"
    assert s5["audit_pass"] is False
    assert s5["payment_link"] is None
    print("[PASS] S5 Compliance Fail:", s5["customer_name"], "Tone Fail -> Halted")

    # 6. S6 Audit Mode (Abusive & Clean Samples)
    abusive_txt = "अरे रमेश! तू पैसे का भरत नाहीस बे? आज संध्याकाळपर्यंत पैसे नाही भरलेस तर तुझ्या घरी पोलीस आणि गुंडे पाठवून अख्ख्या मोहल्ल्यात बेइज्जत करीन!"
    payload = json.dumps({"transcript": abusive_txt}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/api/audit", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    audit_res = json.loads(urllib.request.urlopen(req).read())
    assert audit_res["audit_pass"] is False
    assert audit_res["critical_violations_count"] >= 1
    print("[PASS] S6 Audit Mode: Detected violations =", audit_res["critical_violations_count"])

    # 7. Test Human-in-the-Loop Restructure > Rs 10k shortfall
    restructure_msg = "20,000 भरतो, बाकी 20000 पुढच्या महिन्यात द्या"
    payload = json.dumps({"message": restructure_msg}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/api/cases/1/message", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    paused = json.loads(urllib.request.urlopen(req).read())
    assert paused["status"] == "awaiting_approval"
    print("[PASS] Human-in-Loop: Paused with status =", paused["status"], "shortfall =", paused["data"].get("shortfall_amount"))

    # Approve restructure
    payload = json.dumps({"decision": "approved", "officer": "Senior Credit Lead"}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/api/cases/1/approve", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    resumed = json.loads(urllib.request.urlopen(req).read())
    assert resumed["status"] == "ptp"
    assert resumed["payment_link"] is not None
    print("[PASS] Human-in-Loop: Approved & resumed -> PTP with link:", resumed["payment_link"][:45])

    # 8. Test Evidence Pack
    res = urllib.request.urlopen(f"{BASE}/api/cases/1/evidence-pack")
    ev = json.loads(res.read())
    assert ev["telephony_meta"]["retention_until"] is not None
    assert ev["disclosures_played"]["ai_assistant_identity"] is True
    print("[PASS] Evidence Pack: Valid retention until", ev["telephony_meta"]["retention_until"], "SHA256:", ev["audit_hash"][:16])

if __name__ == "__main__":
    test_full_system_e2e()
