from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import JobStatus, TaskType


class JobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    task_type: TaskType = TaskType.ECHO
    payload: dict[str, Any] = Field(default_factory=dict)
    max_retries: int = Field(default=0, ge=0, le=10)
    timeout_seconds: int = Field(default=30, ge=1, le=300)


class JobRetry(BaseModel):
    max_retries: int | None = Field(default=None, ge=0, le=10)
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)


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
