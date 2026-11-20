import csv
import io
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

FORBIDDEN_COERCIVE_WORDS = [
    "पुलिस", "police", "जेल", "jail", "court", "कोर्ट", "बेशर्म", "चोर", "चीटर",
    "धोखेबाज", "बेइज्जत", "मोहल्ले", "fir", "arrest", "gunda", "पीटेंगे", "उठा लेंगे",
    "shame", "threat", "harass"
]

def audit_batch_transcripts_csv(csv_content: str) -> Dict[str, Any]:
    """
    Batch audit and readiness checklist from call transcripts CSV.
    Input columns: call_id, agent_id, start_time, transcript
    """
    reader = csv.DictReader(io.StringIO(csv_content.strip()))
    
    calls = []
    violations = []
    
    agent_counts = {}
    day_counts = {}
    rule_counts = {
        "POL-DISC-01": 0,    # Mandatory AI / recording disclosure missing
        "POL-HOURS-01": 0,   # Outside 08:00 - 19:00 IST window
        "POL-HARASS-01": 0,  # Coercive / threatening language
        "POL-GRIEV-01": 0,   # Missing grievance details when requested
        "POL-CAP-01": 0      # Calls per borrower per day above cap
    }

    ai_recording_pass_count = 0
    grievance_check_count = 0
    outside_window_count = 0
    harassment_count = 0
    borrower_calls_per_day = {}

    for idx, row in enumerate(reader):
        call_id = str(row.get("call_id") or f"CALL-{idx+1}").strip()
        agent_id = str(row.get("agent_id") or "Agent-1").strip()
        start_time_raw = str(row.get("start_time") or "").strip()
        transcript = str(row.get("transcript") or "").strip()
        transcript_lower = transcript.lower()

        # Parse date and hour
        call_date = "2026-11-20"
        call_hour = 10
        try:
            # Handle formats like 2026-11-20 14:30 or 14:30:00 or ISO
            time_clean = re.sub(r"[T\s]", " ", start_time_raw)
            parts = time_clean.split(" ")
            if len(parts) == 2:
                call_date = parts[0]
                t_parts = parts[1].split(":")
                call_hour = int(t_parts[0])
            elif ":" in start_time_raw:
                t_parts = start_time_raw.split(":")
                call_hour = int(t_parts[0])
        except Exception:
            pass

        day_counts[call_date] = day_counts.get(call_date, 0) + 1
        agent_counts[agent_id] = agent_counts.get(agent_id, 0)

        call_violations = []

        # 1. Calling hours window (08:00 - 19:00 IST)
        if call_hour < 8 or call_hour >= 19:
            outside_window_count += 1
            rule_counts["POL-HOURS-01"] += 1
            v = {
                "call_id": call_id,
                "agent_id": agent_id,
                "date": call_date,
                "rule_id": "POL-HOURS-01",
                "severity": "HIGH",
                "offending_line": f"Call initiated at {start_time_raw} (outside 08:00 - 19:00 IST window)",
                "description": "Violation of permitted outbound calling window (08:00 to 19:00 IST)."
            }
            call_violations.append(v)
            violations.append(v)

        # 2. AI / Recording Disclosure Check
        has_ai_disc = any(k in transcript_lower for k in ["ai assistant", "एआई", "assistant", "automated", "आर्टिफिशियल"])
        has_rec_disc = any(k in transcript_lower for k in ["record", "रेकॉर्ड", "रिकॉर्ड", "दर्ज"])
        
        if has_ai_disc and has_rec_disc:
            ai_recording_pass_count += 1
        else:
            rule_counts["POL-DISC-01"] += 1
            missing = []
            if not has_ai_disc:
                missing.append("AI identity disclosure")
            if not has_rec_disc:
                missing.append("call recording notice")
            v = {
                "call_id": call_id,
                "agent_id": agent_id,
                "date": call_date,
                "rule_id": "POL-DISC-01",
                "severity": "HIGH",
                "offending_line": f"Missing mandatory disclosures: {', '.join(missing)}",
                "description": "Opening turns must disclose AI identity and call recording."
            }
            call_violations.append(v)
            violations.append(v)

        # 3. Coercive / Threatening Language Check
        found_prohibited = [w for w in FORBIDDEN_COERCIVE_WORDS if w in transcript_lower]
        if found_prohibited:
            harassment_count += 1
            rule_counts["POL-HARASS-01"] += 1
            # Extract offending sentence
            offending_sentence = transcript
            for sentence in re.split(r"[.!?\n]", transcript):
                if any(w in sentence.lower() for w in found_prohibited):
                    offending_sentence = sentence.strip()
                    break
            v = {
                "call_id": call_id,
                "agent_id": agent_id,
                "date": call_date,
                "rule_id": "POL-HARASS-01",
                "severity": "CRITICAL",
                "offending_line": f"Coercive phrase: \"{offending_sentence}\" (triggers: {', '.join(found_prohibited)})",
                "description": "Strict prohibition on abusive threats, defamation, or physical harassment."
            }
            call_violations.append(v)
            violations.append(v)

        # 4. Grievance Redressal Officer Check
        borrower_complaint = any(k in transcript_lower for k in ["शिकायत", "complaint", "officer", "nodal", "तक्रार", "अधिकारी"])
        has_grievance_info = any(k in transcript_lower for k in ["nodal", "grievance", "अधिकारी", "1800", "022-", "verma", "वर्मा"])
        if borrower_complaint:
            if has_grievance_info:
                grievance_check_count += 1
            else:
                rule_counts["POL-GRIEV-01"] += 1
                v = {
                    "call_id": call_id,
                    "agent_id": agent_id,
                    "date": call_date,
                    "rule_id": "POL-GRIEV-01",
                    "severity": "MEDIUM",
                    "offending_line": "Borrower raised grievance but no Principal Nodal Officer details were provided.",
                    "description": "Mandatory disclosure of grievance redressal officer on dispute or objection."
                }
                call_violations.append(v)
                violations.append(v)

        # 5. Calls per borrower/account per day check
        account_key = f"{row.get('account_id', call_id)}_{call_date}"
        borrower_calls_per_day[account_key] = borrower_calls_per_day.get(account_key, 0) + 1
        if borrower_calls_per_day[account_key] > 2:
            rule_counts["POL-CAP-01"] += 1
            v = {
                "call_id": call_id,
                "agent_id": agent_id,
                "date": call_date,
                "rule_id": "POL-CAP-01",
                "severity": "HIGH",
                "offending_line": f"Call attempt #{borrower_calls_per_day[account_key]} on {call_date} exceeds daily contact cap (2 calls/day).",
                "description": "Lender contact policy allows maximum 2 calls per borrower per day."
            }
            call_violations.append(v)
            violations.append(v)

        if call_violations:
            agent_counts[agent_id] = agent_counts.get(agent_id, 0) + len(call_violations)

        calls.append({
            "call_id": call_id,
            "agent_id": agent_id,
            "start_time": start_time_raw,
            "violations_count": len(call_violations),
            "status": "PASS" if len(call_violations) == 0 else "FAIL"
        })

    total_calls = max(len(calls), 1)
    disc_pass_rate = round((ai_recording_pass_count / total_calls) * 100, 1)

    critical_violations_count = sum(1 for v in violations if v["severity"] == "CRITICAL")
    readiness_status = "READY" if critical_violations_count == 0 and len(violations) <= 1 else "ACTION_REQUIRED"

    return {
        "checklist": {
            "total_calls_audited": len(calls),
            "ai_recording_disclosure_pass_rate_pct": disc_pass_rate,
            "ai_recording_disclosure_present_count": ai_recording_pass_count,
            "grievance_details_present_count": grievance_check_count,
            "calls_outside_window_count": outside_window_count,
            "calls_above_daily_cap_count": rule_counts["POL-CAP-01"],
            "coercive_language_count": harassment_count,
            "total_violations_found": len(violations),
            "readiness_status": readiness_status,
            "governance_note": "Enforces lender policy (demo); supports RBI conduct rules."
        },
        "violations_by_rule": rule_counts,
        "violations_by_agent": agent_counts,
        "violations_by_day": day_counts,
        "violations": violations,
        "calls_summary": calls
    }

def export_batch_audit_csv(audit_data: Dict[str, Any]) -> str:
    """
    Exports batch audit violations to CSV string.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "call_id",
        "agent_id",
        "date",
        "rule_id",
        "severity",
        "offending_line",
        "description"
    ])
    for v in audit_data.get("violations", []):
        writer.writerow([
            v.get("call_id"),
            v.get("agent_id"),
            v.get("date"),
            v.get("rule_id"),
            v.get("severity"),
            v.get("offending_line"),
            v.get("description")
        ])
    return output.getvalue()
