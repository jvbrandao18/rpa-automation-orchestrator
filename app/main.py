import logging
from collections.abc import Generator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.job_service import can_retry, dumps, job_to_read, mark_terminal, prepare_manual_retry
from app.logging_config import configure_logging, log_event
from app.models import Job, JobStatus
from app.schemas import JobCreate, JobRead, JobRetry
from app.tasks import enqueue_job


configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> Generator[None, None, None]:
    init_db()
    yield


app = FastAPI(
    title="RPA Automation Orchestrator",
    description="Lightweight async job orchestrator with FastAPI, Celery, Redis and SQLite.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs", response_model=JobRead, status_code=201)
def create_job(payload: JobCreate, db: Annotated[Session, Depends(get_db)]) -> JobRead:
    job = Job(
        name=payload.name,
        task_type=payload.task_type.value,
        payload=dumps(payload.payload),
        status=JobStatus.PENDING.value,
        max_retries=payload.max_retries,
        timeout_seconds=payload.timeout_seconds,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        enqueue_job(job.id)
    except Exception as exc:
        mark_terminal(job, JobStatus.FAILED, error=f"queue unavailable: {exc}")
        db.commit()
        log_event(logger, logging.ERROR, "job_enqueue_failed", job_id=job.id, error=str(exc))
        raise HTTPException(status_code=503, detail="job queue is unavailable") from exc

    db.refresh(job)
    log_event(logger, logging.INFO, "job_created", job_id=job.id, task_type=job.task_type)
    return job_to_read(job)


@app.get("/jobs", response_model=list[JobRead])
def list_jobs(
    db: Annotated[Session, Depends(get_db)],
    status: Annotated[JobStatus | None, Query()] = None,
) -> list[JobRead]:
    statement = select(Job).order_by(Job.created_at.desc())
    if status:
        statement = statement.where(Job.status == status.value)
    return [job_to_read(job) for job in db.scalars(statement).all()]


@app.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: str, db: Annotated[Session, Depends(get_db)]) -> JobRead:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job_to_read(job)


@app.post("/jobs/{job_id}/retry", response_model=JobRead)
def retry_job(job_id: str, payload: JobRetry, db: Annotated[Session, Depends(get_db)]) -> JobRead:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if not can_retry(job):
        raise HTTPException(status_code=409, detail=f"job is already {job.status}")

    prepare_manual_retry(job, payload.max_retries, payload.timeout_seconds)
    db.commit()

    try:
        enqueue_job(job.id)
    except Exception as exc:
        mark_terminal(job, JobStatus.FAILED, error=f"queue unavailable: {exc}")
        db.commit()
        log_event(logger, logging.ERROR, "job_retry_enqueue_failed", job_id=job.id, error=str(exc))
        raise HTTPException(status_code=503, detail="job queue is unavailable") from exc

    db.refresh(job)
    log_event(logger, logging.INFO, "job_retry_requested", job_id=job.id)
    return job_to_read(job)


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RPA Automation Orchestrator</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f7f8fb; color: #171923; }
    header { background: #ffffff; border-bottom: 1px solid #e4e7ec; padding: 22px 32px; }
    main { padding: 28px 32px; max-width: 1180px; margin: 0 auto; }
    h1 { margin: 0 0 4px; font-size: 24px; letter-spacing: 0; }
    p { margin: 0; color: #586174; }
    .toolbar { display: flex; gap: 10px; align-items: center; justify-content: space-between; margin-bottom: 18px; }
    .button { border: 1px solid #cfd6e4; background: #ffffff; color: #182033; border-radius: 6px; padding: 9px 13px; cursor: pointer; font-weight: 600; }
    .grid { display: grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap: 10px; margin: 18px 0 24px; }
    .metric { background: #ffffff; border: 1px solid #e4e7ec; border-radius: 8px; padding: 14px; }
    .metric strong { display: block; font-size: 24px; margin-bottom: 2px; }
    .metric span { color: #586174; font-size: 13px; text-transform: uppercase; }
    table { width: 100%; border-collapse: collapse; background: #ffffff; border: 1px solid #e4e7ec; border-radius: 8px; overflow: hidden; }
    th, td { padding: 12px 14px; border-bottom: 1px solid #eef1f5; text-align: left; font-size: 14px; vertical-align: top; }
    th { background: #f0f3f8; color: #343d4f; font-size: 12px; text-transform: uppercase; }
    tr:last-child td { border-bottom: 0; }
    code { background: #f0f3f8; border-radius: 4px; padding: 2px 5px; }
    .status { border-radius: 999px; color: #ffffff; display: inline-flex; font-size: 12px; font-weight: 700; padding: 4px 8px; text-transform: uppercase; }
    .pending { background: #64748b; }
    .running { background: #2563eb; }
    .success { background: #0f766e; }
    .failed { background: #b91c1c; }
    .retrying { background: #b45309; }
    .muted { color: #697386; }
    @media (max-width: 840px) {
      header, main { padding-left: 16px; padding-right: 16px; }
      .grid { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      table { display: block; overflow-x: auto; white-space: nowrap; }
    }
  </style>
</head>
<body>
  <header>
    <h1>RPA Automation Orchestrator</h1>
    <p>Async job execution with retries, timeout handling, and worker-backed lifecycle tracking.</p>
  </header>
  <main>
    <div class="toolbar">
      <p id="last-updated">Loading jobs...</p>
      <button class="button" onclick="loadJobs()">Refresh</button>
    </div>
    <section class="grid" id="metrics"></section>
    <table>
      <thead>
        <tr>
          <th>Status</th>
          <th>Name</th>
          <th>Task</th>
          <th>Attempt</th>
          <th>Timeout</th>
          <th>Result / Error</th>
          <th>Created</th>
        </tr>
      </thead>
      <tbody id="jobs"></tbody>
    </table>
  </main>
  <script>
    const statuses = ["pending", "running", "success", "failed", "retrying"];
    function valueText(job) {
      if (job.error) return job.error;
      if (job.result) return JSON.stringify(job.result);
      return "";
    }
    async function loadJobs() {
      const response = await fetch("/jobs");
      const jobs = await response.json();
      const counts = Object.fromEntries(statuses.map((status) => [status, 0]));
      jobs.forEach((job) => counts[job.status] = (counts[job.status] || 0) + 1);
      document.getElementById("metrics").innerHTML = statuses.map((status) => `
        <div class="metric"><strong>${counts[status]}</strong><span>${status}</span></div>
      `).join("");
      document.getElementById("jobs").innerHTML = jobs.map((job) => `
        <tr>
          <td><span class="status ${job.status}">${job.status}</span></td>
          <td>${job.name}<br><span class="muted"><code>${job.id}</code></span></td>
          <td>${job.task_type}</td>
          <td>${job.attempt} / ${job.max_retries + 1}</td>
          <td>${job.timeout_seconds}s</td>
          <td>${valueText(job)}</td>
          <td>${new Date(job.created_at).toLocaleString()}</td>
        </tr>
      `).join("") || `<tr><td colspan="7" class="muted">No jobs yet.</td></tr>`;
      document.getElementById("last-updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
    }
    loadJobs();
    setInterval(loadJobs, 3000);
  </script>
</body>
</html>
"""
