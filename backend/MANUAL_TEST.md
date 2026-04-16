# Manual Test Guide

## 1. Start the app

Create your runtime env file:

```bash
cp .env.example .env
```

Set a real `GROQ_API_KEY` inside `.env`.

Start everything with one command:

```bash
docker compose up --build
```

The API will be available at:

```text
http://localhost:8000
```

## 2. Health check

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## 3. Upload sample logs

From the `backend/` folder run:

```bash
curl -X POST "http://localhost:8000/upload" \
  -F "logs=@tests/sample_logs/db.log" \
  -F "logs=@tests/sample_logs/app.log" \
  -F "logs=@tests/sample_logs/server.log" \
  -F "incident_start=2025-03-15T02:14:00Z" \
  -F "incident_end=2025-03-15T02:29:00Z" \
  -F "readme=AuthService depends on a shared database pool and nginx fronts login traffic."
```

Copy the returned `incident_id`.

## 4. List incidents

```bash
curl http://localhost:8000/incidents
```

## 5. Fetch one incident

Replace `INCIDENT_ID` below:

```bash
curl http://localhost:8000/incidents/INCIDENT_ID
```

## 6. Analyze correlated events

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

Check that:
- `filtered_events` is non-empty
- `anomaly_clusters` contains DB, AuthService, and nginx clusters
- `cascade_chain` shows service propagation

## 7. Watch SSE progress in another terminal

Run this before the AI step:

```bash
curl -N http://localhost:8000/incidents/INCIDENT_ID/progress
```

You should see streamed events like:

```text
data: {"step":"summarize","status":"running","detail":"Summarizing ..."}
```

## 8. Run the AI pipeline

```bash
curl -X POST "http://localhost:8000/ai/run" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INCIDENT_ID",
    "readme": "AuthService depends on a shared database pool and nginx fronts login traffic."
  }'
```

Expected result:
- HTTP `200`
- progress entries for `summarize`, `rca`, and `report`

## 9. Fetch the RCA JSON

```bash
curl http://localhost:8000/incidents/INCIDENT_ID/rca
```

Check that:
- `confidence` is between `0.0` and `1.0`
- `affected_services` is populated
- timestamps are ISO 8601 UTC

## 10. Fetch the Markdown report

```bash
curl http://localhost:8000/incidents/INCIDENT_ID/report/md
```

Verify the sections appear in this exact order:
- `## Summary`
- `## Incident Timeline`
- `## Root Cause Analysis`
- `## Impact Assessment`
- `## Resolution Steps`
- `## Preventive Actions`
- `## Lessons Learned`

## 11. Download the PDF

```bash
curl -o incident-report.pdf http://localhost:8000/incidents/INCIDENT_ID/report/pdf
```

Check that the file opens and contains:
- cover page
- executive summary
- event timeline table
- RCA and impact sections

## 12. Stop the app

```bash
docker compose down
```

To also remove named volumes:

```bash
docker compose down -v
```
