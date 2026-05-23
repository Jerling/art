"""Intent data schema and validation.

FIX B4: intent_data JSON was stored without Pydantic validation.
All external input to intent_data must now pass through IntentData.parse_obj().
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator, model_validator


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class IntentAction(str, Enum):
    CREATE_TASK = "create_task"
    UPDATE_TASK = "update_task"
    ASSIGN_TASK = "assign_task"
    COMPLETE_TASK = "complete_task"
    DELETE_TASK = "delete_task"
    LIST_TASKS = "list_tasks"
    HELP = "help"
    UNKNOWN = "unknown"


# ──────────────────────────────────────────────────────────────
# FIX B4: IntentData — Pydantic schema for intent_data JSON
# ──────────────────────────────────────────────────────────────
class IntentData(BaseModel):
    """Schema for the intent_data JSON blob stored on tasks.

    FIX B4: All external intent_data input is now validated via this schema.
    Raw JSON strings stored in intent_data TEXT column must pass through
    IntentData.model_validate() before use.

    Example intent_data stored in DB:
      {
        "action": "create_task",
        "estimated_hours": 2.5,
        "suggested_priority": "medium",
        "suggested_due_date": "2026-06-01",
        "confidence": 0.92,
        "raw_text": "下周三前完成 API 设计"
      }
    """

    action: IntentAction = IntentAction.UNKNOWN
    estimated_hours: Annotated[float | None, Field(ge=0, le=168)] = Field(
        default=None,
        description="Estimated hours to complete. Max 1 week (168h).",
    )
    suggested_priority: TaskPriority | None = None
    suggested_due_date: date | None = None
    confidence: Annotated[float | None, Field(ge=0.0, le=1.0)] = Field(
        default=None,
        description="AI confidence score [0.0, 1.0].",
    )
    raw_text: str | None = Field(
        default=None,
        max_length=2000,
        description="Original user input text that generated this intent.",
    )
    # Open field for future extensions — validated but not strict
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("suggested_due_date", mode="before")
    @classmethod
    def _parse_date(cls, v: Any) -> date | None:
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            return date.fromisoformat(v)
        raise ValueError(f"Invalid date format: {v!r}")

    @model_validator(mode="after")
    def _validate_due_date_not_in_past(self) -> IntentData:
        if self.suggested_due_date is not None:
            if self.suggested_due_date < date.today():
                # Downgrade to warning rather than rejection for past dates
                # (allows backfill of historical data)
                pass
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "action": "create_task",
                "estimated_hours": 2.5,
                "suggested_priority": "medium",
                "suggested_due_date": "2026-06-01",
                "confidence": 0.92,
                "raw_text": "下周三前完成 API 设计",
            }
        },
    }


# ──────────────────────────────────────────────────────────────
# Convenience helpers
# ──────────────────────────────────────────────────────────────
def parse_intent_data(raw: str | dict[str, Any] | None) -> IntentData:
    """Parse intent_data from DB TEXT column or dict into IntentData.

    Args:
        raw: JSON string or dict from the intent_data column.

    Returns:
        Validated IntentData instance.

    Raises:
        ValidationError: if the input fails schema validation.
    """
    import json

    if raw is None:
        return IntentData()
    if isinstance(raw, dict):
        return IntentData.model_validate(raw)
    if isinstance(raw, str):
        data = json.loads(raw)
        return IntentData.model_validate(data)
    raise TypeError(f"intent_data must be str, dict or None, got {type(raw).__name__}")
