"""Internal data models for queue and processing."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class InternalEvent(BaseModel):
    """Internal event model for queue and worker processing."""

    event_type: Literal["registration", "purchase"] = Field(..., description="Event type")
    event_id: str = Field(..., description="Unique event identifier")
    received_at: datetime = Field(..., description="Time when event was received by API")
    payload: dict[str, Any] = Field(..., description="Normalized event parameters")
    attempt: int = Field(default=0, description="Current processing attempt number")
    source_meta: dict[str, Any] = Field(
        default_factory=dict,
        description="Source metadata (IP, user-agent, etc, without secrets)",
    )

    def to_stream_fields(self) -> dict[str, str]:
        """Convert to Redis Stream fields (all values must be strings)."""
        return {
            "event_type": self.event_type,
            "event_id": self.event_id,
            "received_at": self.received_at.isoformat(),
            "payload": self.model_dump_json(include={"payload"}),
            "attempt": str(self.attempt),
            "source_meta": self.model_dump_json(include={"source_meta"}),
        }

    @classmethod
    def from_stream_fields(cls, fields: dict[str, str]) -> "InternalEvent":
        """Create InternalEvent from Redis Stream fields."""
        import json

        return cls(
            event_type=fields["event_type"],
            event_id=fields["event_id"],
            received_at=datetime.fromisoformat(fields["received_at"]),
            payload=json.loads(fields["payload"]),
            attempt=int(fields["attempt"]),
            source_meta=json.loads(fields["source_meta"]),
        )
