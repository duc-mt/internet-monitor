from __future__ import annotations

from pydantic import BaseModel


class OutageOut(BaseModel):
    id: int
    started_at: str
    ended_at: str | None
    duration_seconds: float | None
    reason: str | None
    affected_targets: list[str]
    failed_checks: int
    is_active: bool

    model_config = {"from_attributes": True}
