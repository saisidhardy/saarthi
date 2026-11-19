from typing import List, Dict, Any
from app.models import CaseFile, DashboardMetrics
from app.config import settings
from app.database import get_all_cases

def compute_dashboard_metrics(cases: List[CaseFile] = None) -> DashboardMetrics:
    """
    Computes real-time portfolio metrics across the loan book.
    Crucial Rule: Calls that fail compliance audit do NOT count toward valid PTP/recovery.
    """
    if cases is None:
        cases = get_all_cases()

    total_accounts = len(cases)
    if total_accounts == 0:
        return DashboardMetrics(
            total_accounts=0,
            contacted=0,
            ptps=0,
            paid=0,
            escalated=0,
            ptp_conversion_pct=0.0,
            recovery_pct=0.0,
            total_cost_inr=0.0,
            our_cost_per_contact=0.0,
            language_breakdown={}
        )

    contacted_cases = [c for c in cases if c.status != "new"]
    contacted_count = len(contacted_cases)

    # Valid cases: either not audited yet or audit passed (failed audit is excluded from valid recoveries)
    valid_cases = [c for c in cases if c.audit_pass is not False]
    
    ptp_count = sum(1 for c in valid_cases if c.status == "ptp")
    paid_count = sum(1 for c in valid_cases if c.status == "paid")
    escalated_count = sum(1 for c in cases if c.status == "escalated")

    # Conversion % = (PTPs + Paid) / Total Contacted Valid Calls
    valid_contacted = sum(1 for c in contacted_cases if c.audit_pass is not False)
    ptp_conv_pct = round(((ptp_count + paid_count) / max(valid_contacted, 1)) * 100, 1) if valid_contacted > 0 else 0.0

    # Recovery % = Total Paid Amount / Total Book Amount
    total_book_val = sum(c.amount_due for c in cases)
    paid_val = sum(c.amount_due for c in valid_cases if c.status == "paid")
    recovery_pct = round((paid_val / max(total_book_val, 1)) * 100, 1)

    # Cost Tracking: Real computed cost per contact
    total_cost = sum(c.cost_inr for c in contacted_cases)
    avg_cost = round(total_cost / max(contacted_count, 1), 2) if contacted_count > 0 else 0.0

    # Language breakdown
    langs: Dict[str, int] = {}
    for c in cases:
        langs[c.language] = langs.get(c.language, 0) + 1

    return DashboardMetrics(
        total_accounts=total_accounts,
        contacted=contacted_count,
        ptps=ptp_count,
        paid=paid_count,
        escalated=escalated_count,
        ptp_conversion_pct=ptp_conv_pct,
        recovery_pct=recovery_pct,
        total_cost_inr=round(total_cost, 2),
        our_cost_per_contact=avg_cost,
        industry_call_centre_cost=settings.INDUSTRY_CALL_CENTRE_COST,
        industry_field_visit_cost=settings.INDUSTRY_FIELD_VISIT_COST,
        language_breakdown=langs
    )

def run_reporter_agent(case: CaseFile) -> CaseFile:
    """
    Reporter Agent:
    - Calculates the incremental effect of this case on portfolio metrics
    - Appends final report trace item to the case file
    """
    metrics = compute_dashboard_metrics()
    
    case.add_trace(
        agent="Reporter",
        action="Portfolio Metrics & Cost Attribution Synchronized",
        summary=f"Portfolio Updated: Contacted={metrics.contacted}/{metrics.total_accounts}, PTPs={metrics.ptps}, Paid={metrics.paid}, Escalated={metrics.escalated}. Our Cost/Contact: ₹{metrics.our_cost_per_contact:.2f} (vs Industry ₹52.00)."
    )

    return case
