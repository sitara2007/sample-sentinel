from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class DatasetOut(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class SampleIn(BaseModel):
    text: str
    label: str | None = None
    source: str | None = None


class BatchResult(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    idempotency_key: str
    status: str
    received: int
    accepted: int
    rejected: int

    model_config = {"from_attributes": True}


class FlaggedSample(BaseModel):
    sample_id: uuid.UUID
    rule: str
    reason: str


class DatasetReport(BaseModel):
    dataset_id: uuid.UUID
    counts_by_status: dict[str, int]
    duplicate_counts: dict[str, int]
    flagged_samples: list[FlaggedSample]


def parse_sample_item(item: Any) -> SampleIn | None:
    if not isinstance(item, dict):
        return None
    text = item.get("text")
    if not isinstance(text, str):
        return None
    label = item.get("label")
    source = item.get("source")
    if label is not None and not isinstance(label, str):
        return None
    if source is not None and not isinstance(source, str):
        return None
    return SampleIn(text=text, label=label, source=source)
