import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_telephony_outbound_call_dispatch():
    # 1. Dispatch Exotel call
    res = client.post("/api/telephony/call", json={
        "case_id": "23",
        "provider": "exotel",
        "phone": "+919848011223"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["session"]["provider"] == "exotel"
    assert "EXO-" in data["session"]["call_sid"]
    assert "+919848011223" in data["session"]["target_phone"]

def test_telephony_twilio_twiml_generation():
    # 2. Test Twilio TwiML Voice webhook
    res = client.post("/api/telephony/twilio/voice?case_id=23")
    assert res.status_code == 200
    assert "application/xml" in res.headers["content-type"]
    assert "<Response>" in res.text
    assert "<Play>" in res.text

def test_telephony_exotel_flow():
    # 3. Test Exotel flow webhook
    res = client.post("/api/telephony/exotel/flow?case_id=23")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "play_audio_url" in data
    assert "/api/telephony/audio/23" in data["play_audio_url"]

def test_telephony_carrier_audio_stream():
    # 4. Carrier dynamic audio stream
    res = client.get("/api/telephony/audio/23/1")
    assert res.status_code == 200
    assert "audio/mpeg" in res.headers["content-type"]
    assert len(res.content) >= 100

def test_telephony_status_callback():
    # 5. Status callback
    res = client.post("/api/telephony/status", data={
        "CallSid": "EXO-0023-9999",
        "CallStatus": "completed",
        "DialCallDuration": "45"
    })
    assert res.status_code == 200
    assert res.json()["call_status"] == "completed"
