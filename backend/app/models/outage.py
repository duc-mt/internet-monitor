from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class OutageOut(BaseModel):
    id: int
    started_at: str
    ended_at: Optional[str]
    duration_seconds: Optional[float]
    reason: Optional[str]
    affected_targets: List[str]
    failed_checks: int
    is_active: bool

    model_config = {"from_attributes": True}
