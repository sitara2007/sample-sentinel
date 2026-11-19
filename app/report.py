from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditResult, IngestionBatch, Sample
from app.schemas import DatasetReport, FlaggedSample


def build_report(session: Session, dataset_id: uuid.UUID) -> DatasetReport:
    sample_ids = select(Sample.id).where(Sample.dataset_id == dataset_id)
    flagged_ids = select(AuditResult.sample_id).where(AuditResult.sample_id.in_(sample_ids)).distinct()
    flagged_count = session.scalar(select(func.count()).select_from(flagged_ids.subquery())) or 0
    total_samples = session.scalar(select(func.count()).select_from(Sample).where(Sample.dataset_id == dataset_id)) or 0
    accepted_clean = total_samples - flagged_count
    rejected = session.scalar(
        select(func.coalesce(func.sum(IngestionBatch.rejected), 0)).where(
            IngestionBatch.dataset_id == dataset_id
        )
    ) or 0

    dup_rows = session.execute(
        select(AuditResult.rule, func.count(AuditResult.id))
        .where(AuditResult.sample_id.in_(sample_ids))
        .where(AuditResult.rule.in_(("exact_duplicate", "near_duplicate")))
        .group_by(AuditResult.rule)
    ).all()
    duplicate_counts = {"exact_duplicate": 0, "near_duplicate": 0}
    for rule, count in dup_rows:
        duplicate_counts[rule] = int(count)

    flagged_rows = session.execute(
        select(AuditResult.sample_id, AuditResult.rule, AuditResult.detail)
        .where(AuditResult.sample_id.in_(sample_ids))
        .order_by(AuditResult.created_at)
    ).all()
    flagged_samples = [
        FlaggedSample(sample_id=sample_id, rule=rule, reason=detail)
        for sample_id, rule, detail in flagged_rows
    ]

    return DatasetReport(
        dataset_id=dataset_id,
        counts_by_status={
            "accepted": int(accepted_clean),
            "flagged": int(flagged_count),
            "rejected": int(rejected),
        },
        duplicate_counts=duplicate_counts,
        flagged_samples=flagged_samples,
    )
