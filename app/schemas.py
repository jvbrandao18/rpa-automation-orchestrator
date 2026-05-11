from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import JobStatus, TaskType


class JobCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Capture invoice metadata",
                    "task_type": "echo",
                    "payload": {
                        "invoice_id": "INV-100",
                        "source": "vendor_portal",
                        "ticket_id": "INC-1042",
                    },
                    "max_retries": 0,
                    "timeout_seconds": 10,
                }
            ]
        }
    )

    name: str = Field(..., min_length=1, max_length=120, description="Readable support or automation job name.")
    task_type: TaskType = Field(default=TaskType.ECHO, description="Simulated automation behavior to execute.")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Job-specific metadata, such as ticket id, report name, portal name, or record identifiers.",
    )
    max_retries: int = Field(default=0, ge=0, le=10, description="Retry attempts allowed after the first failed run.")
    timeout_seconds: int = Field(default=30, ge=1, le=300, description="Maximum simulated runtime for one attempt.")


class JobRetry(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "max_retries": 1,
                    "timeout_seconds": 15,
                }
            ]
        }
    )

    max_retries: int | None = Field(default=None, ge=0, le=10, description="Optional retry budget override.")
    timeout_seconds: int | None = Field(default=None, ge=1, le=300, description="Optional timeout override.")


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    task_type: TaskType
    payload: dict[str, Any]
    status: JobStatus
    attempt: int
    max_retries: int
    timeout_seconds: int
    celery_task_id: str | None
    error: str | None
    result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
