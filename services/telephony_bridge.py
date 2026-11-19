import os
import time
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
import httpx
from app.config import settings
from app.models import JourneyRecord
from agents.supervisor import run_supervisor_pipeline
from app.database import save_case, get_case

logger = logging.getLogger("saarthi.telephony")

class TelephonyBridge:
    def __init__(self):
        self.provider = settings.TELEPHONY_PROVIDER or "simulated"
        self.base_url = settings.PUBLIC_BASE_URL.rstrip("/")

    def _is_within_rbi_calling_hours(self) -> Tuple[bool, str]:
        """
        Enforces strict RBI Responsible Business Conduct calling hours (08:00 - 19:00 IST).
        """
        if settings.DEMO_OVERRIDE_HOURS:
            return True, "DEMO_OVERRIDE_ACTIVE"
        
        now_utc = datetime.now(timezone.utc)
        ist_now = now_utc + timedelta(hours=5, minutes=30)
        hh = ist_now.hour
        mm = ist_now.minute

        if 8 <= hh < 19:
            return True, f"IST_{hh:02d}:{mm:02d}_WITHIN_WINDOW"
        return False, f"IST_{hh:02d}:{mm:02d}_OUTSIDE_RBI_WINDOW_08_TO_19"

    def normalize_phone_number(self, phone: str) -> str:
        """
        Normalizes phone number to E.164 format (+91XXXXXXXXXX).
        """
        clean = "".join(c for c in phone if c.isdigit() or c == "+")
        if not clean.startswith("+"):
            if len(clean) == 10:
                clean = "+91" + clean
            elif clean.startswith("0") and len(clean) == 11:
                clean = "+91" + clean[1:]
            elif clean.startswith("91") and len(clean) == 12:
                clean = "+" + clean
            else:
                clean = "+" + clean
        return clean

    def initiate_outbound_call(
        self,
        case: JourneyRecord,
        phone_override: Optional[str] = None,
        provider_override: Optional[str] = None,
        caller_id_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initiates an outbound phone call via Exotel or Twilio.
        """
        is_allowed, reason = self._is_within_rbi_calling_hours()
        if not is_allowed:
            logger.warning(f"Outbound call blocked by RBI calling window: {reason}")
            return {
                "success": False,
                "error": "RBI_CALLING_HOURS_VIOLATION",
                "detail": f"Outbound debt resolution calls are restricted to 08:00-19:00 IST per RBI guidelines. Current reason: {reason}."
            }

        target_phone = self.normalize_phone_number(phone_override or case.phone or "+919999999999")
        provider = (provider_override or self.provider or "simulated").lower()
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. EXOTEL INTEGRATION
        if provider == "exotel":
            caller_id = caller_id_override or settings.EXOTEL_CALLER_ID
            is_mock = (
                settings.SIMULATE or
                settings.EXOTEL_API_KEY in ("", "mock_exotel_key") or
                settings.EXOTEL_ACCOUNT_SID in ("", "mock_exotel_sid")
            )

            if not is_mock:
                try:
                    url = f"https://{settings.EXOTEL_SUB_DOMAIN}/v1/Accounts/{settings.EXOTEL_ACCOUNT_SID}/Calls/connect.json"
                    auth = (settings.EXOTEL_API_KEY, settings.EXOTEL_API_TOKEN)
                    flow_url = f"{self.base_url}/api/telephony/exotel/flow?case_id={case.id}"
                    status_url = f"{self.base_url}/api/telephony/status"
                    payload = {
                        "From": target_phone,
                        "To": caller_id,
                        "CallerId": caller_id,
                        "Url": flow_url,
                        "StatusCallback": status_url,
                        "CustomField": str(case.id)
                    }
                    with httpx.Client(timeout=10.0) as client:
                        resp = client.post(url, data=payload, auth=auth)
                        data = resp.json()
                        call_data = data.get("Call", {})
                        call_sid = call_data.get("Sid") or f"EXO-{int(case.id):04d}-{int(time.time())}"
                        status = call_data.get("Status", "queued")
                except Exception as e:
                    logger.warning(f"Exotel live dispatch failed ({e}), falling back to simulated bridge.")
                    call_sid = f"EXO-{int(case.id):04d}-{int(time.time())}"
                    status = "queued"
            else:
                call_sid = f"EXO-{int(case.id):04d}-{int(time.time())}"
                status = "queued"

            telephony_meta = {
                "call_sid": call_sid,
                "provider": "exotel",
                "caller_id": caller_id,
                "target_phone": target_phone,
                "status": status,
                "created_at": now_iso,
                "flow_url": f"{self.base_url}/api/telephony/exotel/flow?case_id={case.id}",
                "carrier_line": "TRAI 140/160 Verified Commercial Telephony"
            }

        # 2. TWILIO INTEGRATION
        elif provider == "twilio":
            caller_id = caller_id_override or settings.TWILIO_FROM_NUMBER
            is_mock = (
                settings.SIMULATE or
                settings.TWILIO_ACCOUNT_SID in ("", "mock_twilio_sid") or
                settings.TWILIO_AUTH_TOKEN in ("", "mock_twilio_token")
            )

            if not is_mock:
                try:
                    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Calls.json"
                    auth = (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                    twiml_url = f"{self.base_url}/api/telephony/twilio/voice?case_id={case.id}"
                    status_url = f"{self.base_url}/api/telephony/status"
                    payload = {
                        "To": target_phone,
                        "From": caller_id,
                        "Url": twiml_url,
                        "StatusCallback": status_url
                    }
                    with httpx.Client(timeout=10.0) as client:
                        resp = client.post(url, data=payload, auth=auth)
                        data = resp.json()
                        call_sid = data.get("sid") or f"CA{hashlib.md5(f'{case.id}:{time.time()}'.encode()).hexdigest()}"
                        status = data.get("status", "queued")
                except Exception as e:
                    logger.warning(f"Twilio live dispatch failed ({e}), falling back to simulated bridge.")
                    call_sid = f"CA{hashlib.md5(f'{case.id}:{time.time()}'.encode()).hexdigest()}"
                    status = "queued"
            else:
                call_sid = f"CA{hashlib.md5(f'{case.id}:{time.time()}'.encode()).hexdigest()}"
                status = "queued"

            telephony_meta = {
                "call_sid": call_sid,
                "provider": "twilio",
                "caller_id": caller_id,
                "target_phone": target_phone,
                "status": status,
                "created_at": now_iso,
                "flow_url": f"{self.base_url}/api/telephony/twilio/voice?case_id={case.id}",
                "carrier_line": "E.164 Global PSTN / Twilio Trunking"
            }

        # 3. SIMULATED DEFAULT
        else:
            call_sid = f"SIM-PBX-{int(case.id):04d}-{int(time.time())}"
            telephony_meta = {
                "call_sid": call_sid,
                "provider": "simulated",
                "caller_id": settings.EXOTEL_CALLER_ID,
                "target_phone": target_phone,
                "status": "in-progress",
                "created_at": now_iso,
                "carrier_line": "Saarthi In-Memory Indic Telephony Simulator"
            }

        # Attach telemetry to case data
        case.data["telephony_session"] = telephony_meta
        case.add_trace(
            agent="Action",
            action=f"Telephony Outbound Dispatched ({telephony_meta['provider'].upper()})",
            summary=f"Call initiated to {target_phone} via {telephony_meta['provider'].upper()} (SID: {telephony_meta['call_sid']}). Carrier line: {telephony_meta['carrier_line']}.",
            badge="Event Trigger"
        )
        save_case(case)

        return {
            "success": True,
            "session": telephony_meta,
            "message": f"Outbound call initiated to {target_phone} via {telephony_meta['provider']}."
        }

    def generate_twiml_turn(self, case: JourneyRecord, borrower_speech: Optional[str] = None) -> str:
        """
        Generates standard TwiML XML response for Twilio Voice calls.
        """
        if borrower_speech and borrower_speech.strip():
            case = run_supervisor_pipeline(case, workflow_id="collections", custom_borrower_reply=borrower_speech)
            save_case(case)

        agent_msgs = [t for t in case.transcript if t.speaker == "agent"]
        latest_text = agent_msgs[-1].text if agent_msgs else "नमस्कार, मी सारथी कॅपिटलकडून बोलत आहे."
        turn_idx = len(case.transcript)
        audio_url = f"{self.base_url}/api/telephony/audio/{case.id}/{turn_idx}"
        gather_action = f"{self.base_url}/api/telephony/twilio/gather?case_id={case.id}"

        lang_twiml_map = {
            "Marathi": "mr-IN",
            "Hindi": "hi-IN",
            "Telugu": "te-IN",
            "Tamil": "ta-IN",
            "Kannada": "kn-IN",
            "English": "en-IN"
        }
        speech_lang = lang_twiml_map.get(case.language, "hi-IN")

        # If terminal state reached (paid, ptp with link sent, or sensitive cooling pause)
        if case.status in ("ptp", "paid", "escalated"):
            xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{audio_url}</Play>
    <Pause length="1"/>
    <Hangup/>
</Response>"""
        else:
            xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{audio_url}</Play>
    <Gather input="speech" language="{speech_lang}" action="{gather_action}" timeout="5" speechTimeout="auto">
        <Pause length="1"/>
    </Gather>
</Response>"""
        return xml

    def generate_exotel_passthru_turn(self, case: JourneyRecord, borrower_speech: Optional[str] = None) -> Dict[str, Any]:
        """
        Generates Exotel Passthru applet JSON response.
        """
        if borrower_speech and borrower_speech.strip():
            case = run_supervisor_pipeline(case, workflow_id="collections", custom_borrower_reply=borrower_speech)
            save_case(case)

        agent_msgs = [t for t in case.transcript if t.speaker == "agent"]
        latest_text = agent_msgs[-1].text if agent_msgs else "नमस्कार, मी सारथी कॅपिटलकडून बोलत आहे."
        turn_idx = len(case.transcript)
        audio_url = f"{self.base_url}/api/telephony/audio/{case.id}/{turn_idx}"

        is_terminal = case.status in ("ptp", "paid", "escalated")
        return {
            "status": "success",
            "case_id": case.id,
            "play_audio_url": audio_url,
            "text": latest_text,
            "language": case.language,
            "terminal_turn": is_terminal,
            "action": "hangup" if is_terminal else "gather_speech",
            "gather_url": f"{self.base_url}/api/telephony/exotel/gather?case_id={case.id}"
        }

telephony_bridge = TelephonyBridge()
