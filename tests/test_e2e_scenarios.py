import json
import pytest
from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_full_system_e2e():
    # 0. Reset book first
    res = client.post("/api/load-sample-book?workflow_id=collections")
    assert res.status_code == 200

    # 1. S1 Hero Test (Sunita Patil)
    res = client.post("/api/events/scenario/s1")
    assert res.status_code == 200
    s1 = res.json()
    assert s1["status"] == "ptp"
    print("[PASS] S1 Hero:", s1["customer_name"], s1["status"])

    # S1 Simulate Payment -> Flips to PAID
    res = client.post("/api/cases/1/simulate-payment")
    assert res.status_code == 200
    s1_paid = res.json()
    assert s1_paid["status"] == "paid"
    print("[PASS] S1 Simulate Pay -> Status is now PAID")

    # 2. S2 Part Payment (Rajesh Sharma)
    res = client.post("/api/events/scenario/s2")
    assert res.status_code == 200
    s2 = res.json()
    assert s2["status"] == "ptp"
    assert s2["data"]["policy_firewall"]["rule_id"] == "POLICY-PART-MIN01"
    print("[PASS] S2 Part-Pay:", s2["customer_name"], s2["data"]["policy_firewall"]["rule_id"])

    # 3. S3 Adversarial Waiver Block (Vikram Malhotra)
    res = client.post("/api/events/scenario/s3")
    assert res.status_code == 200
    s3 = res.json()
    assert s3["status"] == "escalated"
    assert s3["data"]["policy_firewall"]["status"] == "BLOCKED"
    assert s3["data"]["policy_firewall"]["rule_id"] == "POLICY-WAIVER-NO01"
    assert s3["payment_link"] is None
    print("[PASS] S3 Adversarial Block:", s3["customer_name"], s3["data"]["policy_firewall"]["rule_id"], "Zero Link")

    # 4. S4 Sensitive Pause (Suresh Patil)
    res = client.post("/api/events/scenario/s4")
    assert res.status_code == 200
    s4 = res.json()
    assert s4["status"] == "escalated"
    assert s4["data"]["policy_firewall"]["status"] == "SENSITIVE_PAUSE"
    assert s4["data"]["policy_firewall"]["rule_id"] == "FAIR-PRAC-SENS01"
    assert s4["do_not_contact_until"] is not None
    follow_up = s4["data"].get("human_follow_up_task", "")
    assert "insurance" in follow_up.lower()
    print("[PASS] S4 Sensitive Pause + Human Task:", s4["customer_name"], follow_up)

    # 5. S7 T-24h Preventive Rescue (Anjali Deshmukh)
    res = client.post("/api/events/scenario/s7")
    assert res.status_code == 200
    s7 = res.json()
    assert s7["status"] == "ptp"
    assert s7["data"]["policy_firewall"]["rule_id"] == "POLICY-PREV-FEE01"
    print("[PASS] S7 T-24h Rescue:", s7["customer_name"], "Rescheduled debit window")

    # 6. S8 Kirana Cashflow 4x Micro-Split (Sunita Patil)
    res = client.post("/api/events/scenario/s8")
    assert res.status_code == 200
    s8 = res.json()
    assert s8["status"] == "ptp"
    assert s8["data"]["policy_firewall"]["rule_id"] == "POLICY-MICRO-SPLIT01"
    micro = s8.get("micro_schedule") or s8["data"].get("micro_schedule")
    assert len(micro) == 4
    assert micro[0]["amount_inr"] == 10000.0
    print("[PASS] S8 Micro-Split:", s8["customer_name"], "4 Tranches AutoPay")

    # 7. S5 Bad Transcript Threat (Manoj Kumar)
    res = client.post("/api/events/scenario/s5")
    assert res.status_code == 200
    s5 = res.json()
    assert s5["status"] == "escalated"
    assert s5["audit_pass"] is False
    assert s5["payment_link"] is None
    print("[PASS] S5 Compliance Fail:", s5["customer_name"], "Tone Fail -> Halted")

    # 8. S6 Audit Mode (Abusive & Clean Samples)
    abusive_txt = "अरे रमेश! तू पैसे का भरत नाहीस बे? आज संध्याकाळपर्यंत पैसे नाही भरलेस तर तुझ्या घरी पोलीस आणि गुंडे पाठवून अख्ख्या मोहल्ल्यात बेइज्जत करीन!"
    res = client.post("/api/audit", json={"transcript": abusive_txt})
    assert res.status_code == 200
    audit_res = res.json()
    assert audit_res["audit_pass"] is False
    assert audit_res["critical_violations_count"] >= 1
    print("[PASS] S6 Audit Mode: Detected violations =", audit_res["critical_violations_count"])

    # 9. Test Human-in-the-Loop Restructure > Rs 10k shortfall
    restructure_msg = "20,000 भरतो, बाकी 20000 पुढच्या महिन्यात द्या"
    res = client.post("/api/cases/1/message", json={"message": restructure_msg})
    assert res.status_code == 200
    paused = res.json()
    assert paused["status"] == "awaiting_approval"
    print("[PASS] Human-in-Loop: Paused with status =", paused["status"], "shortfall =", paused["data"].get("shortfall_amount"))

    # Approve restructure
    res = client.post("/api/cases/1/approve", json={"decision": "approved", "officer": "Senior Credit Lead"})
    assert res.status_code == 200
    resumed = res.json()
    assert resumed["status"] == "ptp"
    print("[PASS] Human-in-Loop: Approved & resumed -> PTP")

    # 10. Test Evidence Pack
    res = client.get("/api/cases/1/evidence-pack")
    assert res.status_code == 200
    ev = res.json()
    assert ev["telephony_meta"]["retention_until"] is not None
    assert ev["disclosures_played"]["ai_assistant_identity"] is True
    print("[PASS] Evidence Pack: Valid retention until", ev["telephony_meta"]["retention_until"], "SHA256:", ev["audit_hash"][:16])

if __name__ == "__main__":
    test_full_system_e2e()
