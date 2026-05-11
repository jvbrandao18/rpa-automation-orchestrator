# RPA Automation Orchestrator

A small FastAPI service for submitting, queueing, running, retrying, and monitoring simulated RPA automation jobs.

This repository is intentionally simple. It is designed to show the backend support-engineering patterns behind an automation platform without pretending to be a full enterprise orchestrator.

## What is it?

RPA Automation Orchestrator is a lightweight job orchestration API. A support engineer or upstream system can submit an automation job, let a background worker execute it, and inspect the job state later through the API or dashboard.

The API can:

- create and enqueue automation jobs
- list jobs and filter them by status
- retrieve a single job
- retry terminal jobs
- track lifecycle states: `pending`, `running`, `success`, `failed`, and `retrying`
- enforce simple timeout behavior
- expose a basic monitoring dashboard
- expose a health check for local and container validation

The automation work is simulated on purpose. The project focuses on orchestration, worker execution, retries, persistence, and observability.

## Why was it built?

Support and RPA teams often manage automations that are slow, flaky, or dependent on external systems such as portals, reports, downloads, forms, and ticketing tools. A direct HTTP request is not a good fit for that kind of work.

This project demonstrates a practical pattern:

- receive automation requests through an API
- persist job details before work starts
- queue execution outside the request cycle
- let workers update job status as work progresses
- record clear failure and timeout information
- allow controlled retries after a failed run

It fits a Python/RPA/AI support engineering portfolio because it shows how automation work can be made visible and recoverable instead of being hidden inside one-off scripts.

## How does it work?

A client submits a job with:

- `name`: readable job label
- `task_type`: one of `echo`, `sleep`, or `fail`
- `payload`: job-specific metadata
- `max_retries`: number of retry attempts after the first failure
- `timeout_seconds`: maximum simulated runtime

The API stores the job in SQLite and publishes work to Redis. A Celery worker consumes the queued task, claims the job, runs the simulated automation, and updates the stored status.

Workers skip jobs that are already running or terminal, which keeps duplicate worker execution from mutating the same job twice.

### Data flow

```text
Client or support tool
        |
        v
FastAPI /jobs endpoint
        |
        | 1. validate request
        | 2. persist job as pending
        v
SQLite jobs table <----------+
        |                    |
        | 3. enqueue job     | 6. update status/result/error
        v                    |
Redis queue                  |
        |                    |
        | 4. consume task    |
        v                    |
Celery worker ---------------+
        |
        | 5. run simulated automation
        v
echo / sleep / fail task behavior
```

### Job lifecycle

```text
pending -> running -> success
pending -> running -> retrying -> running -> failed
pending -> running -> failed
failed  -> retrying -> running -> success or failed
```

### Main technologies

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- SQLite
- Celery
- Redis
- Pytest
- Docker Compose

### API endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Health check |
| `POST` | `/jobs` | Create and enqueue a job |
| `GET` | `/jobs` | List jobs, optionally filtered by status |
| `GET` | `/jobs/{job_id}` | Retrieve a single job |
| `POST` | `/jobs/{job_id}/retry` | Retry a terminal job |
| `GET` | `/dashboard` | Basic job monitoring dashboard |
| `GET` | `/docs` | Swagger API documentation |

### Task types

| Task type | Behavior | Support/RPA example |
| --- | --- | --- |
| `echo` | Returns the provided payload and succeeds | Confirm an invoice, ticket, or customer record was accepted by the workflow |
| `sleep` | Sleeps for `payload.duration` seconds and fails if it exceeds `timeout_seconds` | Simulate waiting for a portal export, report download, or external batch job |
| `fail` | Raises a simulated automation error for retry testing | Simulate a missing button, validation error, login issue, or unavailable page |

## API examples

Create a successful job:

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Capture invoice metadata",
    "task_type": "echo",
    "payload": {
      "invoice_id": "INV-100",
      "source": "vendor_portal",
      "ticket_id": "INC-1042"
    },
    "max_retries": 0,
    "timeout_seconds": 10
  }'
```

Create a job that fails and exercises retry handling:

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Submit vendor portal form",
    "task_type": "fail",
    "payload": {
      "error": "portal returned validation error",
      "ticket_id": "INC-2048"
    },
    "max_retries": 2,
    "timeout_seconds": 10
  }'
```

Create a timeout scenario:

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Wait for daily report export",
    "task_type": "sleep",
    "payload": {
      "duration": 5,
      "report": "daily_settlement"
    },
    "max_retries": 1,
    "timeout_seconds": 2
  }'
```

List failed jobs:

```bash
curl "http://localhost:8000/jobs?status=failed"
```

Retry a terminal job:

```bash
curl -X POST http://localhost:8000/jobs/<job_id>/retry \
  -H "Content-Type: application/json" \
  -d '{
    "max_retries": 1,
    "timeout_seconds": 15
  }'
```

## How do I run it?

### Run with Docker Compose

```bash
docker compose up --build
```

Open:

- Dashboard: `http://localhost:8000/dashboard`
- Swagger docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

Stop the stack:

```bash
docker compose down
```

Reset persisted job data:

```bash
docker compose down -v
```

### Run locally

Local execution requires Redis to be running and reachable through `REDIS_URL`.

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export REDIS_URL=redis://localhost:6379/0
uvicorn app.main:app --reload
```

In another terminal:

```bash
export REDIS_URL=redis://localhost:6379/0
celery -A app.celery_app.celery_app worker --loglevel=info --concurrency=2
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:REDIS_URL = "redis://localhost:6379/0"
uvicorn app.main:app --reload
```

In another PowerShell terminal:

```powershell
$env:REDIS_URL = "redis://localhost:6379/0"
celery -A app.celery_app.celery_app worker --loglevel=info --concurrency=2
```

## Validation

Run the automated tests:

```bash
pytest
```

The test suite runs Celery in eager mode, so Redis is not required for tests.

Check the API locally:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/jobs
```

Check the containerized stack:

```bash
docker compose up --build
docker compose ps
curl http://localhost:8000/health
docker compose down
```

## Project structure

```text
app/
  automation.py       Simulated automation task execution
  celery_app.py       Celery configuration
  config.py           Environment-based settings
  database.py         SQLAlchemy engine and session setup
  job_service.py      Job serialization and state transitions
  logging_config.py   Structured JSON logging
  main.py             FastAPI routes and dashboard
  models.py           SQLAlchemy models and enums
  schemas.py          Pydantic request and response schemas
  tasks.py            Celery worker task and retry scheduling
tests/
  conftest.py         Test settings and database isolation
  test_api.py         API, retry, timeout, and worker behavior tests
docker-compose.yml    API, worker, Redis, and SQLite volume setup
Dockerfile            Runtime image for API and worker services
requirements.txt      Python dependencies
pytest.ini            Pytest configuration
```

## Scope notes

This project does not claim production usage or enterprise readiness. It is a portfolio-sized implementation of the orchestration pattern: API intake, durable job state, worker execution, bounded retries, and simple monitoring.
