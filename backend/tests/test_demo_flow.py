from pathlib import Path

import httpx
import pytest

from main import app
from services.ai_provider import AIProvider, get_provider, set_provider


class MockAIProvider(AIProvider):
    async def complete(self, prompt: str) -> str:
        if 'key "service_summaries"' in prompt:
            return '{"service_summaries":[{"service":"db","error_count":12,"patterns":["connection pool exhausted @ 2025-03-15T02:16:00Z"],"anomalies":["db spike @ 2025-03-15T02:16:10Z"]},{"service":"AuthService","error_count":9,"patterns":["db timeout @ 2025-03-15T02:18:10Z"],"anomalies":["retry storm @ 2025-03-15T02:18:25Z"]},{"service":"nginx","error_count":8,"patterns":["503 spike @ 2025-03-15T02:19:45Z"],"anomalies":["gateway degradation @ 2025-03-15T02:19:50Z"]}]}'
        if "produce a valid RCAOutput JSON object" in prompt:
            return '{"root_cause":"Database connection pool exhaustion evidenced at 2025-03-15T02:16:00Z.","confidence":0.93,"confidence_reasoning":"Direct pool exhaustion and downstream timeout timestamps align.","evidence":[{"timestamp":"2025-03-15T02:16:00Z","service":"db","log_line":"connection pool exhausted","significance":"Initial failure point"},{"timestamp":"2025-03-15T02:18:10Z","service":"AuthService","log_line":"database timeout","significance":"Downstream propagation"},{"timestamp":"2025-03-15T02:19:45Z","service":"nginx","log_line":"POST /login HTTP/1.1 -> 503","significance":"User-facing impact"}],"cascade_chain":["db → AuthService","AuthService → nginx"],"affected_services":[{"service":"db","impact_level":"HIGH","error_count":12},{"service":"AuthService","impact_level":"HIGH","error_count":9},{"service":"nginx","impact_level":"MED","error_count":8}],"estimated_downtime_minutes":11,"first_anomaly_timestamp":"2025-03-15T02:16:00Z","resolution_timestamp":"2025-03-15T02:27:00Z"}'
        return """## Summary

Database connection pool exhaustion began at 2025-03-15T02:16:00Z and cascaded into authentication and gateway failures.

The user-facing login path was degraded by 2025-03-15T02:19:45Z until recovery signals appeared at 2025-03-15T02:27:00Z.

## Incident Timeline
- 2025-03-15T02:16:00Z db pool exhausted
- 2025-03-15T02:18:10Z AuthService timed out
- 2025-03-15T02:19:45Z nginx returned 503

## Root Cause Analysis
Database connection pool exhaustion caused the incident.

## Impact Assessment
Login requests returned 503 responses.

## Resolution Steps
- Increased available DB connections.
- Drained hung sessions.

## Preventive Actions
- Add pool saturation alerts.
- Rate limit retries.

## Lessons Learned
- Propagation was detectable before customer impact.
"""


@pytest.mark.asyncio
async def test_demo_flow():
    original = get_provider()
    set_provider(MockAIProvider())
    try:
        logs_dir = Path(__file__).parent / "sample_logs"
        files = [("logs", (name, (logs_dir / name).read_bytes(), "text/plain")) for name in ["db.log", "app.log", "server.log"]]
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000", timeout=60.0) as client:
            upload = await client.post("/upload", files=files, data={"incident_start": "2025-03-15T02:14:00Z", "incident_end": "2025-03-15T02:29:00Z", "readme": "Auth service depends on shared db pool."})
            upload.raise_for_status()
            incident_id = upload.json()["incident_id"]
            analyzed = await client.post("/analyze", json={"incident_id": incident_id, "start_time": "2025-03-15T02:14:00Z", "end_time": "2025-03-15T02:29:00Z", "context": "demo"})
            analyzed.raise_for_status()
            assert analyzed.json()["filtered_events"]
            ran = await client.post("/ai/run", json={"incident_id": incident_id, "readme": "Auth service depends on shared db pool."})
            ran.raise_for_status()
            rca = await client.get(f"/incidents/{incident_id}/rca")
            assert 0.0 <= rca.json()["confidence"] <= 1.0
            pdf = await client.get(f"/incidents/{incident_id}/report/pdf")
            assert pdf.headers["content-type"].startswith("application/pdf")
            assert len(pdf.content) > 10000
    finally:
        set_provider(original)
