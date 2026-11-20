from typing import List, Dict, Any, Optional
from app.models import JourneyRecord, EngineMetrics, WorkflowStep
from app.config import settings
from app.database import get_all_cases

def compute_engine_metrics(workflow_id: str = "collections", records: List[JourneyRecord] = None) -> EngineMetrics:
    """
    Computes workflow engine-level simulation metrics across synthetic accounts.
    Shows ONLY counts the engine computes (contacted, PTPs, blocked by policy, escalated)
    plus cost per contact computed from usage counters x /policies/pricing.yaml, labelled 'estimated'.
    Industry figures reported by other sources are kept distinct as external benchmarks.
    """
    if records is None:
        records = get_all_cases(workflow_id=workflow_id)

    total_records = len(records)
    started_records = [r for r in records if r.status != "new"]
    started_count = len(started_records)

    # Valid records
    valid_records = [r for r in records if r.audit_pass is not False]
    
    # Human-touch / escalated records
    escalated_records = [r for r in records if r.status == "escalated" or r.assigned_human]
    human_touch_count = len(escalated_records)
    human_touch_rate = round((human_touch_count / max(started_count, 1)) * 100, 1) if started_count > 0 else 0.0

    total_cost = sum(r.cost_inr for r in started_records)

    if workflow_id == "loan_sales":
        completed_autonomously = sum(1 for r in valid_records if r.status in ("qualified", "completed") and r.status != "escalated")
        cost_per_completed = round(total_cost / max(completed_autonomously, 1), 2) if completed_autonomously > 0 else 0.0
        conversion_rate = round((completed_autonomously / max(started_count, 1)) * 100, 1) if started_count > 0 else 0.0

        return EngineMetrics(
            workflow_id="loan_sales",
            workflow_name="Pre-Approved Personal Loan Sales",
            journeys_started=started_count,
            journeys_completed_autonomously=completed_autonomously,
            human_touch_count=human_touch_count,
            human_touch_rate_pct=human_touch_rate,
            total_cost_inr=round(total_cost, 2),
            cost_per_completed_journey=cost_per_completed,
            workflow_metric_name="Qualified Leads Conversion",
            workflow_metric_value=conversion_rate,
            industry_call_centre_cost=settings.INDUSTRY_CALL_CENTRE_COST,
            industry_field_visit_cost=settings.INDUSTRY_FIELD_VISIT_COST,
            details={
                "qualified": completed_autonomously,
                "escalated": human_touch_count,
                "total_leads": total_records
            }
        )
    else:
        ptp_count = sum(1 for r in valid_records if r.status == "ptp")
        paid_count = sum(1 for r in valid_records if r.status == "paid")
        completed_autonomously = ptp_count + paid_count
        cost_per_completed = round(total_cost / max(completed_autonomously, 1), 2) if completed_autonomously > 0 else 0.0

        from services.sarvam import sarvam_service
        live_pricing = sarvam_service.get_cost_summary()

        # Cost per contact computed from actual usage counters and pricing.yaml
        avg_cost_contact = live_pricing.get("cost_per_contact_inr", 1.68)

        blocked_by_policy = sum(
            1 for r in records 
            if r.data.get("policy_firewall", {}).get("status") == "BLOCKED" or r.audit_pass is False
        )
        lang_split = {}
        for r in records:
            lang_split[r.language] = lang_split.get(r.language, 0) + 1

        cash_rec_today = sum(float(r.instant_recovered_inr or 0.0) for r in valid_records)
        future_locked = sum(float(r.locked_mandate_inr or 0.0) for r in valid_records)

        return EngineMetrics(
            workflow_id="collections",
            workflow_name="Early Delinquency Collections (EMI)",
            journeys_started=started_count,
            journeys_completed_autonomously=completed_autonomously,
            human_touch_count=human_touch_count,
            human_touch_rate_pct=human_touch_rate,
            total_cost_inr=round(total_cost, 2),
            cost_per_completed_journey=cost_per_completed,
            workflow_metric_name="Simulated PTP Resolution",
            workflow_metric_value=ptp_count,
            industry_call_centre_cost=52.00,
            industry_field_visit_cost=250.00,
            recovery_lift_pct=None,
            baseline_recovery_pct=None,
            portfolio_recovery_rate_pct=None,
            total_bounce_fees_saved_inr=0.0,
            npa_loans_rescued_count=completed_autonomously,
            cash_recovered_today_inr=round(cash_rec_today, 2),
            future_cash_locked_inr=round(future_locked, 2),
            npa_and_fees_prevented_inr=0.0,
            details={
                "simulation_label": f"Simulation on {total_records} synthetic accounts",
                "total_accounts": total_records,
                "contacted": started_count,
                "ptps": ptp_count,
                "paid": paid_count,
                "escalated": human_touch_count,
                "blocked_by_policy": blocked_by_policy,
                "language_split": lang_split,
                "our_cost_per_contact": avg_cost_contact,
                "cost_label": live_pricing.get("cost_label", "estimated"),
                "footnote": live_pricing.get("footnote", "excludes LLM tokens"),
                "bounced_emi_fee_range": live_pricing.get("bounced_emi_fee_range", "Rs 50-150 per bounced EMI (PayU, citing CRISIL)"),
                "field_visit_cost_range": live_pricing.get("field_visit_cost_range", "Rs 250-500 per field visit (Business Standard)"),
                "benchmark_label": live_pricing.get("benchmark_label", "industry figures reported by other sources"),
                "cash_recovered_today_inr": round(cash_rec_today, 2),
                "future_cash_locked_inr": round(future_locked, 2)
            }
        )

# Alias for backward compatibility
compute_dashboard_metrics = compute_engine_metrics

def run_reporter_agent(record: JourneyRecord, step: Optional[WorkflowStep] = None, context: Optional[Dict[str, Any]] = None) -> JourneyRecord:
    workflow_id = record.workflow_id or (context.get("workflow_id") if context else "collections")
    metrics = compute_engine_metrics(workflow_id)
    
    record.add_trace(
        agent="Reporter",
        action="Engine Simulation Metrics Synchronized",
        summary=f"Simulation State: Contacted={metrics.journeys_started}, PTPs={metrics.details.get('ptps', 0)}, Escalated={metrics.human_touch_count}, Blocked={metrics.details.get('blocked_by_policy', 0)}. Est Cost/Contact: ₹{metrics.details.get('our_cost_per_contact', 1.68)}."
    )

    return record
