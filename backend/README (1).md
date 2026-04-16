# Autonomous Log-to-Incident Report Generator

Backend-only FastAPI service that:

- accepts 1..N log files from multiple services
- parses mixed log formats into a unified event model
- correlates events inside an incident time window
- detects anomaly clusters and cascade chains
- runs a 3-stage LangGraph AI pipeline using Groq
- stores incidents, events, RCA output, and reports in SQLite
- exposes results through REST and SSE
- generates Markdown and PDF incident reports

## Features

- FastAPI + Pydantic v2 + async SQLAlchemy
- SQLite persistence with async `aiosqlite`
- Multi-format parser:
  - syslog
  - Apache/Nginx access logs
  - app logs with ISO timestamps
  - JSON logs
- Event correlator with:
  - time-window filtering
  - cross-file chronological ordering
  - anomaly cluster detection
  - cascade-chain detection
- LangGraph pipeline:
  - error summarization
  - root cause analysis
  - post-mortem writing
- SSE progress streaming
- PDF generation using `reportlab`
- Dockerized one-command startup
- automated parser and integration tests

## Folder Structure

```text
backend/
├── main.py
├── models/
├── prompts/
├── routers/
├── services/
├── tests/
├── .env.example
├── .dockerignore
├── docker-compose.yml
├── Dockerfile
├── MANUAL_TEST.md
├── README.md
└── requirements.txt
```

## Tech Stack

- Python `3.11`
- FastAPI
- Pydantic `2.8.2`
- SQLAlchemy `2.0.x`
- LangGraph `0.2.28`
- Groq Python SDK
- SQLite + `aiosqlite`
- ReportLab
- Pytest + HTTPX

## How It Works

### 1. Upload

Client uploads multiple log files and an incident time window to `/upload`.

### 2. Parse

The backend parses all files into a shared `LogEvent` schema.

### 3. Correlate

`/analyze` filters events to the requested interval, sorts them, detects anomaly clusters, and derives cascade chains.

### 4. AI Pipeline

`/ai/run` runs the 3-node LangGraph pipeline:

1. summarize errors
2. perform RCA
3. write Markdown post-mortem

### 5. Persist

Incidents, events, RCA JSON, and report metadata are stored in SQLite.

### 6. Retrieve

Clients fetch:

- incident summaries
- event timelines
- RCA JSON
- Markdown report
- PDF report
- SSE progress events

## Environment Variables

Copy `.env.example` to `.env` and set values as needed.

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.1-8b-instant
DATABASE_URL=sqlite+aiosqlite:///./incidents.db
TMP_DIR=/tmp/incidents
LOG_LEVEL=INFO
ALLOWED_ORIGINS=http://localhost:3000,https://*.vercel.app
```

### Notes

- `GROQ_API_KEY` is required for real AI runs.
- `GROQ_MODEL` defaults to `llama-3.1-8b-instant`, a smaller Groq-hosted model suited to fast, higher-throughput workloads.
- In Docker, `DATABASE_URL` and `TMP_DIR` are overridden by `docker-compose.yml`.
- Tests do not need a real Groq key because they use a mocked AI provider.

## Run The App

### Option 1: Docker, single command

This is the easiest way to run the whole app.

1. Create a runtime env file:

```bash
cp .env.example .env
```

2. Put your real Groq key in `.env`.

3. Start the app:

```bash
docker compose up --build
```

4. Open:

```text
http://localhost:8000
http://localhost:8000/docs
```

### Option 2: Local Python

```bash
python -m pip install -r requirements.txt
uvicorn main:app --reload
```

## Docker Details

The Docker setup includes:

- multi-stage build
- non-root runtime user
- health check on `/health`
- persistent SQLite storage volume
- persistent temp/report volume

### Docker Commands

Start:

```bash
docker compose up --build
```

Stop:

```bash
docker compose down
```

Stop and remove volumes:

```bash
docker compose down -v
```

## API Overview

Base URL:

```text
http://localhost:8000
```

### Health

#### `GET /health`

Checks service health.

Response:

```json
{"status":"ok"}
```

### Upload

#### `POST /upload`

Uploads one or more log files.

Content type:

```text
multipart/form-data
```

Fields:

- `logs`: repeated file field, required
- `incident_start`: ISO 8601 UTC string, required
- `incident_end`: ISO 8601 UTC string, required
- `readme`: optional context string

Example:

```bash
curl -X POST "http://localhost:8000/upload" \
  -F "logs=@tests/sample_logs/db.log" \
  -F "logs=@tests/sample_logs/app.log" \
  -F "logs=@tests/sample_logs/server.log" \
  -F "incident_start=2025-03-15T02:14:00Z" \
  -F "incident_end=2025-03-15T02:29:00Z" \
  -F "readme=AuthService depends on a shared database pool and nginx fronts login traffic."
```

Example response:

```json
{
  "incident_id": "2e9bb8ae-16b8-4e76-8c56-0e92d69d40a0",
  "status": "parsing",
  "total_events": 210,
  "error_count": 51,
  "warn_count": 15,
  "duration_minutes": 15,
  "affected_services": ["AuthService", "db", "nginx"],
  "created_at": "2026-04-16T10:00:00Z"
}
```

### List Incidents

#### `GET /incidents`

Returns all stored incident summaries.

Example:

```bash
curl http://localhost:8000/incidents
```

### Get One Incident

#### `GET /incidents/{incident_id}`

Returns a single `IncidentSummary`.

Example:

```bash
curl http://localhost:8000/incidents/INCIDENT_ID
```

### Get Events

#### `GET /incidents/{incident_id}/events`

Returns all stored parsed events for an incident.

Example:

```bash
curl http://localhost:8000/incidents/INCIDENT_ID/events
```

### Analyze Correlated Events

#### `POST /analyze`

Filters and correlates events inside the incident window.

Request:

```json
{
  "incident_id": "uuid",
  "start_time": "2025-03-15T02:14:00Z",
  "end_time": "2025-03-15T02:29:00Z",
  "context": "Manual validation run"
}
```

Example:

```bash
curl -X POST "http://localhost:8000/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INCIDENT_ID",
    "start_time": "2025-03-15T02:14:00Z",
    "end_time": "2025-03-15T02:29:00Z",
    "context": "Manual validation run"
  }'
```

What to expect:

- `filtered_events` contains the in-window timeline
- `anomaly_clusters` contains services with 5+ errors in 60 seconds
- `cascade_chain` describes propagation like `db → AuthService`
- `service_stats` summarizes totals, errors, and warnings

### Run AI Pipeline

#### `POST /ai/run`

Starts the LangGraph pipeline for a stored incident.

Request:

```json
{
  "incident_id": "uuid",
  "readme": "optional additional context"
}
```

Example:

```bash
curl -X POST "http://localhost:8000/ai/run" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INCIDENT_ID",
    "readme": "AuthService depends on a shared database pool and nginx fronts login traffic."
  }'
```

Success response includes:

- `incident_id`
- `progress`
- `report_path`

### Get RCA

#### `GET /incidents/{incident_id}/rca`

Returns the stored RCA JSON.

Example:

```bash
curl http://localhost:8000/incidents/INCIDENT_ID/rca
```

Important fields:

- `root_cause`
- `confidence`
- `evidence`
- `cascade_chain`
- `affected_services`
- `first_anomaly_timestamp`
- `resolution_timestamp`

### Get Markdown Report

#### `GET /incidents/{incident_id}/report/md`

Returns the report as plain Markdown text.

Example:

```bash
curl http://localhost:8000/incidents/INCIDENT_ID/report/md
```

Expected sections:

- `## Summary`
- `## Incident Timeline`
- `## Root Cause Analysis`
- `## Impact Assessment`
- `## Resolution Steps`
- `## Preventive Actions`
- `## Lessons Learned`

### Download PDF Report

#### `GET /incidents/{incident_id}/report/pdf`

Downloads the generated PDF.

Example:

```bash
curl -o incident-report.pdf http://localhost:8000/incidents/INCIDENT_ID/report/pdf
```

Expected response header:

```text
Content-Type: application/pdf
```

### Watch Progress with SSE

#### `GET /incidents/{incident_id}/progress`

Streams progress events as `text/event-stream`.

Example:

```bash
curl -N http://localhost:8000/incidents/INCIDENT_ID/progress
```

Example stream:

```text
data: {"step":"summarize","status":"running","detail":"Summarizing 210 correlated events"}

data: {"step":"summarize","status":"done","detail":"Service summaries created"}

data: {"step":"rca","status":"running","detail":"Performing root cause analysis"}
```

## Full API Test Procedure

This is the shortest practical way to explain and test the API manually.

### Brief Procedure

1. Start the backend with `docker compose up --build`.
2. Open `http://localhost:8000/health` to verify the app is up.
3. Upload the sample logs using `/upload`.
4. Copy the returned `incident_id`.
5. Call `/analyze` for that incident window.
6. In another terminal, watch `/incidents/{incident_id}/progress`.
7. Call `/ai/run`.
8. Fetch `/incidents/{incident_id}/rca`.
9. Fetch `/incidents/{incident_id}/report/md`.
10. Download `/incidents/{incident_id}/report/pdf`.

### Manual Validation Checklist

- upload returns HTTP `200`
- incident summary contains `incident_id`
- analyze returns non-empty `filtered_events`
- `anomaly_clusters` contains expected services
- SSE emits `summarize`, `rca`, and `report`
- RCA confidence is between `0.0` and `1.0`
- markdown report contains all required sections
- PDF downloads and opens successfully

## Sample End-to-End Test Case

### Test Case: Database Pool Exhaustion Cascade

Goal:

Verify that the backend detects a DB-first failure pattern that propagates to `AuthService` and then `nginx`.

Input files:

- `tests/sample_logs/db.log`
- `tests/sample_logs/app.log`
- `tests/sample_logs/server.log`

Incident window:

- `2025-03-15T02:14:00Z`
- `2025-03-15T02:29:00Z`

System context:

```text
AuthService depends on a shared database pool and nginx fronts login traffic.
```

Expected behavior:

- parser reads all 3 files successfully
- `/analyze` returns `filtered_events` > 0
- `/analyze` identifies DB, AuthService, and nginx anomaly activity
- cascade chain reflects upstream-to-downstream propagation
- `/ai/run` completes successfully
- `/rca` points to DB connection pool exhaustion as root cause
- `/report/pdf` returns a valid PDF larger than trivial size

Example execution:

```bash
curl -X POST "http://localhost:8000/upload" \
  -F "logs=@tests/sample_logs/db.log" \
  -F "logs=@tests/sample_logs/app.log" \
  -F "logs=@tests/sample_logs/server.log" \
  -F "incident_start=2025-03-15T02:14:00Z" \
  -F "incident_end=2025-03-15T02:29:00Z" \
  -F "readme=AuthService depends on a shared database pool and nginx fronts login traffic."
```

Then:

```bash
curl -X POST "http://localhost:8000/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INCIDENT_ID",
    "start_time": "2025-03-15T02:14:00Z",
    "end_time": "2025-03-15T02:29:00Z",
    "context": "database pool exhaustion scenario"
  }'
```

Then:

```bash
curl -X POST "http://localhost:8000/ai/run" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INCIDENT_ID",
    "readme": "AuthService depends on a shared database pool and nginx fronts login traffic."
  }'
```

Expected RCA characteristics:

- `root_cause` mentions DB pool exhaustion
- `confidence` is bounded in `[0.0, 1.0]`
- `affected_services` includes `db`, `AuthService`, and `nginx`

## Automated Testing

### Run all tests

```bash
pytest tests -v
```

### Run parser tests only

```bash
pytest tests/test_parser.py -v
```

### Run integration flow only

```bash
pytest tests/test_demo_flow.py -v
```

### What the tests cover

`tests/test_parser.py`

- syslog parsing
- Apache/Nginx parsing
- app log parsing
- JSON log parsing
- mixed-format parsing

`tests/test_demo_flow.py`

- upload sample logs
- analyze incident
- run mocked AI pipeline
- fetch RCA
- download PDF

## Error Handling Notes

The API returns structured HTTP errors for:

- invalid request data
- missing incidents
- missing reports
- AI provider failures
- parsing or analysis failures

Typical statuses:

- `200 OK`
- `400 Bad Request`
- `404 Not Found`
- `500 Internal Server Error`

## Data Model Summary

Main stored entities:

- `incidents`
- `log_events`
- `rca_results`
- `reports`

Generated outputs:

- parsed normalized events
- correlation results
- RCA JSON
- Markdown post-mortem
- PDF post-mortem report

## Useful URLs

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health: `http://localhost:8000/health`

## Quick Demo Script

If you just want a very short demo path:

1. `docker compose up --build`
2. `curl http://localhost:8000/health`
3. upload the 3 sample logs
4. call `/analyze`
5. call `/ai/run`
6. fetch `/incidents/{id}/rca`
7. download `/incidents/{id}/report/pdf`

## Notes For Reviewers

- Timestamps are normalized to UTC.
- All JSON keys use `snake_case`.
- All Groq calls flow through `get_provider().complete(...)`.
- The SSE endpoint stays open until the report step is done or errors.
- The integration test uses a mocked AI provider so it is deterministic and does not require external API access.
