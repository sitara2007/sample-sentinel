from __future__ import annotations

import asyncio
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import commit_with_retry
from app.embeddings import cosine_similarity, encode, load_model
from app.hashing import content_hash
from app.models import AuditResult, Dataset, IngestionBatch, Sample
from app.schemas import BatchResult, SampleIn, parse_sample_item

log = structlog.get_logger(__name__)


def get_dataset_or_none(session: Session, dataset_id: uuid.UUID) -> Dataset | None:
    return session.get(Dataset, dataset_id)


def create_dataset(session: Session, name: str) -> Dataset:
    dataset = Dataset(name=name)
    session.add(dataset)
    commit_with_retry(session)
    session.refresh(dataset)
    return dataset


def _add_audit(session: Session, sample_id: uuid.UUID, rule: str, severity: str, detail: str) -> None:
    session.add(
        AuditResult(sample_id=sample_id, rule=rule, severity=severity, detail=detail)
    )


def _existing_by_hash(session: Session, dataset_id: uuid.UUID, digest: str) -> Sample | None:
    return session.scalar(
        select(Sample).where(Sample.dataset_id == dataset_id, Sample.content_hash == digest)
    )


def _insert_sample(session: Session, dataset_id: uuid.UUID, item: SampleIn, digest: str) -> Sample | None:
    sample = Sample(
        dataset_id=dataset_id,
        content_hash=digest,
        text=item.text,
        label=item.label,
        source=item.source,
    )
    try:
        with session.begin_nested():
            session.add(sample)
            session.flush()
        return sample
    except IntegrityError:
        return None


def _quality_audits(session: Session, sample: Sample) -> None:
    if len(sample.text.strip()) < 20:
        _add_audit(
            session,
            sample.id,
            "too_short",
            "warning",
            "text length after strip is under 20 characters",
        )
    if sample.label is None or not sample.label.strip():
        _add_audit(session, sample.id, "empty_label", "warning", "label is null or blank")


def _near_match_detail(new_text: str, others: list[tuple[uuid.UUID, str]], threshold: float) -> str | None:
    if load_model() is None:
        return None
    vector = encode(new_text)
    if vector is None:
        return None
    for other_id, other_text in others:
        other_vec = encode(other_text)
        if other_vec is None:
            continue
        score = cosine_similarity(vector, other_vec)
        if score >= threshold:
            return f"cosine similarity {score:.4f} with sample {other_id} (>= {threshold})"
    return None


def _process_one(session: Session, dataset_id: uuid.UUID, raw_item: object) -> Sample | None:
    parsed = parse_sample_item(raw_item)
    if parsed is None:
        log.info("schema_invalid", dataset_id=str(dataset_id))
        return None

    digest = content_hash(parsed.text)
    existing = _existing_by_hash(session, dataset_id, digest)
    if existing is not None:
        _add_audit(
            session,
            existing.id,
            "exact_duplicate",
            "warning",
            "SHA-256 of normalized text already exists in this dataset",
        )
        return None

    sample = _insert_sample(session, dataset_id, parsed, digest)
    if sample is None:
        existing = _existing_by_hash(session, dataset_id, digest)
        if existing is not None:
            _add_audit(
                session,
                existing.id,
                "exact_duplicate",
                "warning",
                "SHA-256 of normalized text already exists in this dataset",
            )
        return None

    _quality_audits(session, sample)
    return sample


async def ingest_samples(
    session: Session,
    dataset_id: uuid.UUID,
    items: list[object],
    idempotency_key: str,
) -> BatchResult:
    settings = get_settings()
    existing = session.scalar(
        select(IngestionBatch).where(IngestionBatch.idempotency_key == idempotency_key)
    )
    if existing is not None:
        log.info("idempotent_replay", key=idempotency_key, batch_id=str(existing.id))
        return BatchResult.model_validate(existing)

    accepted_samples: list[Sample] = []
    rejected = 0
    for raw_item in items:
        sample = _process_one(session, dataset_id, raw_item)
        if sample is None:
            rejected += 1
        else:
            accepted_samples.append(sample)

    if accepted_samples and load_model() is not None:
        all_rows = session.scalars(select(Sample).where(Sample.dataset_id == dataset_id)).all()
        semaphore = asyncio.Semaphore(settings.max_concurrency)

        async def check(sample: Sample) -> tuple[uuid.UUID, str] | None:
            others = [(row.id, row.text) for row in all_rows if row.id != sample.id]
            async with semaphore:
                detail = await asyncio.to_thread(
                    _near_match_detail, sample.text, others, settings.threshold
                )
            if detail is None:
                return None
            return sample.id, detail

        matches = await asyncio.gather(*(check(sample) for sample in accepted_samples))
        for match in matches:
            if match is not None:
                sample_id, detail = match
                _add_audit(session, sample_id, "near_duplicate", "warning", detail)

    batch = IngestionBatch(
        dataset_id=dataset_id,
        idempotency_key=idempotency_key,
        status="completed",
        received=len(items),
        accepted=len(accepted_samples),
        rejected=rejected,
    )
    session.add(batch)
    commit_with_retry(session)
    session.refresh(batch)
    log.info(
        "batch_ingested",
        dataset_id=str(dataset_id),
        received=len(items),
        accepted=batch.accepted,
        rejected=batch.rejected,
    )
    return BatchResult.model_validate(batch)
