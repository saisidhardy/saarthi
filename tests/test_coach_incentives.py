from fastapi.testclient import TestClient
from app.main import app
from services.coach import record_consent, run_full_cashflow_coach

client = TestClient(app)

def test_borrower_repayment_gains_computation():
    record_consent("kirana_owner", True)
    data = run_full_cashflow_coach("kirana_owner")
    assert "borrower_repayment_gains" in data
    gains = data["borrower_repayment_gains"]
    assert gains["immediate_fee_saved_inr"] > 0
    assert gains["accelerated_interest_saved_inr"] > 0
    assert gains["tenure_months_saved"] >= 1
    assert "whatsapp_message_en" in gains
    assert "whatsapp_message_hi" in gains

def test_send_coach_incentive_message_endpoint():
    record_consent("kirana_owner", True)
    resp = client.post("/api/coach/send-incentive-message", json={
        "persona_id": "kirana_owner",
        "channel": "whatsapp",
        "language": "en"
    })
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "success"
    assert "immediate_saved_inr" in res_data
    assert "accelerated_interest_saved_inr" in res_data
    assert "Hi Sunita" in res_data["message"]
