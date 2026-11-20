import csv
import io
import re
from typing import List, Dict, Any, Optional

def parse_bool(val: Any) -> bool:
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in ("y", "yes", "true", "1", "t")

def parse_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        clean = re.sub(r"[^\d.]", "", str(val))
        return float(clean) if clean else default
    except Exception:
        return default

def parse_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        clean = re.sub(r"[^\d-]", "", str(val))
        return int(clean) if clean else default
    except Exception:
        return default

def get_dpd_bucket(dpd: int) -> str:
    if dpd <= 7:
        return "1–7 DPD"
    elif dpd <= 15:
        return "8–15 DPD"
    elif dpd <= 30:
        return "16–30 DPD"
    else:
        return "30+ DPD"

def compute_group_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_n = len(rows)
    if total_n == 0:
        return {
            "n": 0,
            "ptp_kept_rate_pct": 0.0,
            "recovery_rate_pct": 0.0,
            "total_recovered_inr": 0.0,
            "small_sample": True
        }

    ptp_rows = [r for r in rows if r.get("ptp_date") and str(r.get("ptp_date")).strip()]
    total_ptps = len(ptp_rows)
    ptps_kept = sum(1 for r in ptp_rows if parse_bool(r.get("paid")))
    ptp_kept_rate = round((ptps_kept / total_ptps) * 100, 1) if total_ptps > 0 else 0.0

    paid_rows = [r for r in rows if parse_bool(r.get("paid"))]
    paid_count = len(paid_rows)
    recovery_rate = round((paid_count / total_n) * 100, 1)
    total_recovered = round(sum(parse_float(r.get("paid_amount"), 0.0) for r in paid_rows), 2)

    return {
        "n": total_n,
        "total_ptps": total_ptps,
        "ptps_kept": ptps_kept,
        "ptp_kept_rate_pct": ptp_kept_rate,
        "paid_count": paid_count,
        "recovery_rate_pct": recovery_rate,
        "total_recovered_inr": total_recovered,
        "small_sample": total_n < 30
    }

def analyze_outcomes_csv(csv_content: str) -> Dict[str, Any]:
    """
    Parses outcomes CSV: account_id, group[saarthi|baseline], paid[y/n], paid_amount, paid_date, ptp_date
    Optional: dpd, language
    Computes PTP-kept rate and recovery rate by DPD bucket and language, with n and small sample warning (<30).
    Provides side-by-side comparison if both groups exist.
    """
    reader = csv.DictReader(io.StringIO(csv_content.strip()))
    
    rows = []
    for idx, r in enumerate(reader):
        account_id = str(r.get("account_id") or f"ACC-{idx+1}").strip()
        group = str(r.get("group") or "saarthi").strip().lower()
        if "base" in group:
            group = "baseline"
        else:
            group = "saarthi"

        paid = r.get("paid")
        paid_amount = parse_float(r.get("paid_amount"), 0.0)
        paid_date = str(r.get("paid_date") or "").strip()
        ptp_date = str(r.get("ptp_date") or "").strip()
        dpd = parse_int(r.get("dpd"), 5)
        language = str(r.get("language") or "Hindi").strip()

        rows.append({
            "account_id": account_id,
            "group": group,
            "paid": paid,
            "paid_amount": paid_amount,
            "paid_date": paid_date,
            "ptp_date": ptp_date,
            "dpd": dpd,
            "dpd_bucket": get_dpd_bucket(dpd),
            "language": language
        })

    groups_present = list(set(r["group"] for r in rows))
    has_saarthi = "saarthi" in groups_present
    has_baseline = "baseline" in groups_present
    is_side_by_side = has_saarthi and has_baseline

    # Overall stats
    overall_all = compute_group_stats(rows)
    saarthi_rows = [r for r in rows if r["group"] == "saarthi"]
    baseline_rows = [r for r in rows if r["group"] == "baseline"]

    saarthi_overall = compute_group_stats(saarthi_rows)
    baseline_overall = compute_group_stats(baseline_rows)

    # By DPD bucket
    dpd_buckets = ["1–7 DPD", "8–15 DPD", "16–30 DPD", "30+ DPD"]
    by_dpd = []
    for bucket in dpd_buckets:
        b_rows_s = [r for r in saarthi_rows if r["dpd_bucket"] == bucket]
        b_rows_b = [r for r in baseline_rows if r["dpd_bucket"] == bucket]
        
        stat_s = compute_group_stats(b_rows_s)
        stat_b = compute_group_stats(b_rows_b)
        
        by_dpd.append({
            "bucket": bucket,
            "saarthi": stat_s,
            "baseline": stat_b,
            "total_n": len(b_rows_s) + len(b_rows_b),
            "small_sample": (len(b_rows_s) + len(b_rows_b)) < 30
        })

    # By Language
    all_languages = sorted(list(set(r["language"] for r in rows)))
    by_lang = []
    for lang in all_languages:
        l_rows_s = [r for r in saarthi_rows if r["language"].lower() == lang.lower()]
        l_rows_b = [r for r in baseline_rows if r["language"].lower() == lang.lower()]

        stat_s = compute_group_stats(l_rows_s)
        stat_b = compute_group_stats(l_rows_b)

        by_lang.append({
            "language": lang,
            "saarthi": stat_s,
            "baseline": stat_b,
            "total_n": len(l_rows_s) + len(l_rows_b),
            "small_sample": (len(l_rows_s) + len(l_rows_b)) < 30
        })

    return {
        "total_records": len(rows),
        "is_side_by_side": is_side_by_side,
        "overall": {
            "saarthi": saarthi_overall,
            "baseline": baseline_overall,
            "combined": overall_all
        },
        "by_dpd_bucket": by_dpd,
        "by_language": by_lang,
        "sample_warning_threshold": 30,
        "note": "Metrics reflect imported outcome records. Small sample warning flagged when n < 30."
    }
