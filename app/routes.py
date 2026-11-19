from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.ingest import create_dataset, get_dataset_or_none, ingest_samples
from app.report import build_report
from app.schemas import BatchResult, DatasetCreate, DatasetOut, DatasetReport

router = APIRouter()


@router.post("/datasets", response_model=DatasetOut, status_code=201)
def post_dataset(payload: DatasetCreate, session: Session = Depends(get_db)) -> DatasetOut:
    dataset = create_dataset(session, payload.name)
    return DatasetOut.model_validate(dataset)


@router.post("/datasets/{dataset_id}/samples", response_model=BatchResult)
async def post_samples(
    dataset_id: uuid.UUID,
    items: list[Any],
    session: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> BatchResult:
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    settings = get_settings()
    if len(items) > settings.batch_size:
        raise HTTPException(status_code=400, detail=f"batch size exceeds {settings.batch_size}")
    dataset = get_dataset_or_none(session, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return await ingest_samples(session, dataset_id, items, idempotency_key.strip())


@router.get("/datasets/{dataset_id}/report", response_model=DatasetReport)
def get_report(dataset_id: uuid.UUID, session: Session = Depends(get_db)) -> DatasetReport:
    dataset = get_dataset_or_none(session, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return build_report(session, dataset_id)
