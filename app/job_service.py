import json
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Job, JobStatus, utc_now
from app.schemas import JobRead


TERMINAL_STATUSES = {
    JobStatus.SUCCESS.value,
    JobStatus.FAILED.value,
}

EXECUTABLE_STATUSES = {
    JobStatus.PENDING.value,
    JobStatus.RETRYING.value,
}


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def can_retry(job: Job) -> bool:
    return job.status in TERMINAL_STATUSES


def can_execute(job: Job) -> bool:
    return job.status in EXECUTABLE_STATUSES


def has_retry_budget(job: Job) -> bool:
    return job.attempt <= job.max_retries


def mark_running(job: Job, task_id: str | None) -> None:
    job.attempt += 1
    job.status = JobStatus.RUNNING.value
    job.started_at = utc_now()
    job.finished_at = None
    job.error = None
    job.result = None
    job.celery_task_id = task_id
    job.updated_at = utc_now()


def claim_job_for_execution(db: Session, job_id: str, task_id: str | None) -> Job | None:
    now = utc_now()
    result = db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status.in_(EXECUTABLE_STATUSES))
        .values(
            status=JobStatus.RUNNING.value,
            attempt=Job.attempt + 1,
            started_at=now,
            finished_at=None,
            error=None,
            result=None,
            celery_task_id=task_id,
            updated_at=now,
        )
    )
    db.commit()
    if result.rowcount != 1:
        return None
    return db.get(Job, job_id)


def mark_retrying(job: Job, error: str) -> None:
    job.status = JobStatus.RETRYING.value
    job.error = error
    job.updated_at = utc_now()


def mark_terminal(job: Job, status: JobStatus, error: str | None = None, result: dict[str, Any] | None = None) -> None:
    job.status = status.value
    job.error = error
    job.result = dumps(result) if result is not None else None
    job.finished_at = utc_now()
    job.updated_at = utc_now()


def prepare_manual_retry(job: Job, max_retries: int | None, timeout_seconds: int | None) -> None:
    if max_retries is not None:
        job.max_retries = max_retries
    if timeout_seconds is not None:
        job.timeout_seconds = timeout_seconds

    job.status = JobStatus.RETRYING.value
    job.attempt = 0
    job.error = None
    job.result = None
    job.started_at = None
    job.finished_at = None
    job.updated_at = utc_now()


def job_to_read(job: Job) -> JobRead:
    return JobRead(
        id=job.id,
        name=job.name,
        task_type=job.task_type,
        payload=loads(job.payload, {}),
        status=job.status,
        attempt=job.attempt,
        max_retries=job.max_retries,
        timeout_seconds=job.timeout_seconds,
        celery_task_id=job.celery_task_id,
        error=job.error,
        result=loads(job.result, None),
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
