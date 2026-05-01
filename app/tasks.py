import logging
from typing import Any

from sqlalchemy.orm import Session

from app.automation import AutomationTimeoutError, run_automation
from app.celery_app import celery_app
from app.database import SessionLocal, init_db
from app.job_service import claim_job_for_execution, has_retry_budget, loads, mark_retrying, mark_terminal
from app.logging_config import log_event
from app.models import Job, JobStatus, utc_now


logger = logging.getLogger(__name__)


def enqueue_job(job_id: str, countdown: int = 0) -> str:
    task = run_job.apply_async(args=[job_id], countdown=countdown)
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job:
            job.celery_task_id = task.id
            job.updated_at = utc_now()
            db.commit()
    log_event(logger, logging.INFO, "job_enqueued", job_id=job_id, task_id=task.id, countdown=countdown)
    return task.id


def _schedule_retry(db: Session, job: Job, error: str) -> bool:
    mark_retrying(job, error)
    db.commit()
    log_event(
        logger,
        logging.WARNING,
        "job_retry_scheduled",
        job_id=job.id,
        attempt=job.attempt,
        max_retries=job.max_retries,
        error=error,
    )
    try:
        enqueue_job(job.id, countdown=1)
    except Exception as exc:
        mark_terminal(job, JobStatus.FAILED, error=f"retry queue unavailable: {exc}")
        db.commit()
        log_event(logger, logging.ERROR, "job_retry_enqueue_failed", job_id=job.id, error=str(exc))
        return False
    return True


@celery_app.task(name="app.tasks.run_job", bind=True)
def run_job(self, job_id: str) -> dict[str, Any] | None:
    init_db()
    with SessionLocal() as db:
        job = claim_job_for_execution(db, job_id, getattr(self.request, "id", None))
        if not job:
            existing_job = db.get(Job, job_id)
            if not existing_job:
                log_event(logger, logging.WARNING, "job_missing", job_id=job_id)
                return None
            log_event(logger, logging.INFO, "job_skipped", job_id=existing_job.id, status=existing_job.status)
            return {"status": existing_job.status, "attempt": existing_job.attempt, "skipped": True}

        attempt = job.attempt
        log_event(logger, logging.INFO, "job_started", job_id=job.id, attempt=attempt, task_type=job.task_type)

        payload = loads(job.payload, {})

        try:
            result = run_automation(job.task_type, payload, job.timeout_seconds)
        except AutomationTimeoutError as exc:
            if has_retry_budget(job):
                if _schedule_retry(db, job, str(exc)):
                    return {"status": JobStatus.RETRYING.value, "attempt": attempt}
                return {"status": JobStatus.FAILED.value, "attempt": attempt}
            mark_terminal(job, JobStatus.FAILED, error=f"timeout: {exc}")
            db.commit()
            log_event(logger, logging.ERROR, "job_timeout", job_id=job.id, attempt=attempt, error=str(exc))
            return {"status": JobStatus.FAILED.value, "attempt": attempt}
        except Exception as exc:
            if has_retry_budget(job):
                if _schedule_retry(db, job, str(exc)):
                    return {"status": JobStatus.RETRYING.value, "attempt": attempt}
                return {"status": JobStatus.FAILED.value, "attempt": attempt}
            mark_terminal(job, JobStatus.FAILED, error=str(exc))
            db.commit()
            log_event(logger, logging.ERROR, "job_failed", job_id=job.id, attempt=attempt, error=str(exc))
            return {"status": JobStatus.FAILED.value, "attempt": attempt}

        mark_terminal(job, JobStatus.SUCCESS, result=result)
        db.commit()
        log_event(logger, logging.INFO, "job_succeeded", job_id=job.id, attempt=attempt)
        return {"status": JobStatus.SUCCESS.value, "attempt": attempt, "result": result}
