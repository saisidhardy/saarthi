from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_integrations_status():
    response = client.get("/api/v1/integrations/status")
    assert response.status_code == 200
    data = response.json()
    assert "lms" in data
    assert "byot" in data
    assert "pricing_tier" in data
    assert data["lms"]["status"] == "connected"
    assert data["byot"]["status"] == "active"

def test_case_sync_and_call_dispatch():
    sync_payload = {
        "external_loan_id": "TEST-LMS-LOAN-99",
        "lender_id": "demo_lender_b",
        "customer_name": "Ramesh Verma",
        "phone": "+919811122233",
        "language": "Hindi",
        "amount_due": 12500.0,
        "dpd": 6,
        "loan_type": "MSME Working Capital",
        "source_lms": "FinnOne Neo"
    }
    sync_resp = client.post("/api/v1/cases/sync", json=sync_payload)
    assert sync_resp.status_code == 200
    sync_data = sync_resp.json()
    assert sync_data["status"] == "success"
    assert sync_data["external_loan_id"] == "TEST-LMS-LOAN-99"
    case_id = sync_data["case_id"]

    dispatch_resp = client.post("/api/v1/calls/dispatch", json={
        "case_id": case_id,
        "channel": "voice",
        "telephony_provider": "Exotel Enterprise SIP",
        "dlt_header": "140921-BAJAJ"
    })
    assert dispatch_resp.status_code == 200
    dispatch_data = dispatch_resp.json()
    assert dispatch_data["dispatched"] is True
    assert "conversation_state" in dispatch_data
    assert "sha256_audit_hash" in dispatch_data["conversation_state"]

    cb_resp = client.get(f"/api/v1/callbacks/ptp/{case_id}")
    assert cb_resp.status_code == 200
    cb_data = cb_resp.json()
    assert cb_data["event"] == "PROMISE_TO_PAY_RECORDED"
    assert cb_data["external_loan_id"] == "TEST-LMS-LOAN-99"

def test_byot_config_update():
    update_payload = {
        "provider": "Tata Tele Services",
        "dlt_header": "140999-TATA",
        "sip_trunk_uri": "sip.mumbai.tatatele.com",
        "caller_id_whitelist": ["+911409990001"],
        "data_residency_region": "ap-south-1 (Mumbai, India)"
    }
    resp = client.post("/api/v1/integrations/byot/config", json=update_payload)
    assert resp.status_code == 200
    assert resp.json()["byot"]["provider"] == "Tata Tele Services"
