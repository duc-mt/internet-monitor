from __future__ import annotations

import ipaddress
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import MIN_INTERVAL_SECONDS

Protocol = Literal["icmp", "tcp"]

# A conservative RFC-1123-ish hostname pattern: labels of alphanumerics and
# hyphens (not leading/trailing with a hyphen), joined by dots.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)"
    r"(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


def validate_host(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("host must not be empty")
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    if _HOSTNAME_RE.match(value):
        return value
    raise ValueError(f"{value!r} is not a valid hostname or IP address")


class TargetBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    host: str = Field(..., min_length=1, max_length=253)
    protocol: Protocol = "icmp"
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    is_gateway: bool = False
    enabled: bool = True
    interval_seconds: int = Field(default=5, ge=MIN_INTERVAL_SECONDS, le=3600)

    @field_validator("host")
    @classmethod
    def _validate_host(cls, v: str) -> str:
        return validate_host(v)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v

    @model_validator(mode="after")
    def _tcp_needs_port_or_default(self) -> "TargetBase":
        # TCP checks need a port; ICMP ignores it. Rather than reject a
        # missing port for TCP targets, default to 443 (works for the vast
        # majority of reachable hosts) so the API stays forgiving.
        if self.protocol == "tcp" and self.port is None:
            self.port = 443
        return self


class TargetCreate(TargetBase):
    pass


class TargetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    host: Optional[str] = Field(default=None, min_length=1, max_length=253)
    protocol: Optional[Protocol] = None
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    is_gateway: Optional[bool] = None
    enabled: Optional[bool] = None
    interval_seconds: Optional[int] = Field(default=None, ge=MIN_INTERVAL_SECONDS, le=3600)

    @field_validator("host")
    @classmethod
    def _validate_host(cls, v: Optional[str]) -> Optional[str]:
        return validate_host(v) if v is not None else v


class TargetOut(TargetBase):
    id: int
    created_at: str

    model_config = {"from_attributes": True}
