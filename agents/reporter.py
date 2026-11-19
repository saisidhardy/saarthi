from typing import List, Dict, Any, Optional
from app.models import JourneyRecord, EngineMetrics, WorkflowStep
from app.config import settings
from app.database import get_all_cases

def compute_engine_metrics(workflow_id: str = "collections", records: List[JourneyRecord] = None) -> EngineMetrics:
    """
    Computes workflow engine-level metrics across journey records.
    Engine Metrics:
    - Journeys started
    - Journeys completed autonomously
    - Human-touch rate %
    - Cost per completed journey
    - Workflow's own metric (recovery % for collections, qualified leads for sales)
    """
    if records is None:
        records = get_all_cases(workflow_id=workflow_id)

    total_records = len(records)
    started_records = [r for r in records if r.status != "new"]
    started_count = len(started_records)

    # Valid records (failed audits do not count as completed autonomously)
    valid_records = [r for r in records if r.audit_pass is not False]
    
    # Human-touch records
    escalated_records = [r for r in records if r.status == "escalated" or r.assigned_human]
    human_touch_count = len(escalated_records)
    human_touch_rate = round((human_touch_count / max(started_count, 1)) * 100, 1) if started_count > 0 else 0.0

    total_cost = sum(r.cost_inr for r in started_records)

    if workflow_id == "loan_sales":
        # Loan Sales metrics
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
        # Collections metrics
        ptp_count = sum(1 for r in valid_records if r.status == "ptp")
        paid_count = sum(1 for r in valid_records if r.status == "paid")
        completed_autonomously = ptp_count + paid_count
        cost_per_completed = round(total_cost / max(completed_autonomously, 1), 2) if completed_autonomously > 0 else 0.0

        total_book_val = sum(r.amount_due for r in records)
        paid_val = sum(r.amount_due for r in valid_records if r.status == "paid")
        recovery_pct = round((paid_val / max(total_book_val, 1)) * 100, 1)

        from services.sarvam import sarvam_service
        live_pricing = sarvam_service.get_cost_summary()

        # Average cost per contact (computed live from actual usage and pricing.yaml rates)
        avg_cost_contact = round(total_cost / max(started_count, 1), 2) if started_count > 0 else live_pricing.get("cost_per_contact_inr", 1.68)

        blocked_by_policy = sum(
            1 for r in records 
            if r.data.get("policy_firewall", {}).get("status") == "BLOCKED" or r.audit_pass is False
        )
        lang_split = {}
        for r in records:
            lang_split[r.language] = lang_split.get(r.language, 0) + 1

        ptp_conv_pct = round(((ptp_count + paid_count) / max(started_count, 1)) * 100, 1) if started_count > 0 else 0.0

        return EngineMetrics(
            workflow_id="collections",
            workflow_name="Early Delinquency Collections (EMI)",
            journeys_started=started_count,
            journeys_completed_autonomously=completed_autonomously,
            human_touch_count=human_touch_count,
            human_touch_rate_pct=human_touch_rate,
            total_cost_inr=round(total_cost, 2),
            cost_per_completed_journey=cost_per_completed,
            workflow_metric_name="Recovery Rate",
            workflow_metric_value=recovery_pct,
            industry_call_centre_cost=settings.INDUSTRY_CALL_CENTRE_COST,
            industry_field_visit_cost=settings.INDUSTRY_FIELD_VISIT_COST,
            details={
                "total_accounts": total_records,
                "contacted": started_count,
                "ptps": ptp_count,
                "paid": paid_count,
                "escalated": human_touch_count,
                "blocked_by_policy": blocked_by_policy,
                "ptp_conversion_pct": ptp_conv_pct,
                "language_split": lang_split,
                "recovery_pct": recovery_pct,
                "our_cost_per_contact": avg_cost_contact,
                "cost_label": live_pricing.get("cost_label", "estimated from published rates"),
                "footnote": live_pricing.get("footnote", "excludes LLM tokens"),
                "industry_call_centre_cost": live_pricing.get("industry_call_centre_cost", 52.00),
                "industry_field_visit_cost": live_pricing.get("industry_field_visit_cost", 250.00),
                "benchmark_label": live_pricing.get("benchmark_label", "reported by other sources")
            }
        )

# Alias for backward compatibility
compute_dashboard_metrics = compute_engine_metrics

def run_reporter_agent(record: JourneyRecord, step: Optional[WorkflowStep] = None, context: Optional[Dict[str, Any]] = None) -> JourneyRecord:
    """
    Generic Reporter Agent:
    - Calculates the incremental effect of this journey on engine metrics
    - Appends final report trace item to the record
    """
    workflow_id = record.workflow_id or (context.get("workflow_id") if context else "collections")
    metrics = compute_engine_metrics(workflow_id)
    
    record.add_trace(
        agent="Reporter",
        action="Engine Metrics & Attribution Synchronized",
        summary=f"Engine State Updated: Started={metrics.journeys_started}, Autonomous Completed={metrics.journeys_completed_autonomously}, Human-Touch Rate={metrics.human_touch_rate_pct}%. Cost/Completed: ₹{metrics.cost_per_completed_journey:.2f}."
    )

    return record
