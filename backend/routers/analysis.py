import asyncio
import logging

from fastapi import APIRouter, HTTPException

from models.schemas import AnalyzeRequest, IncidentStatus
from services.ai_pipeline import progress_queues
from services.event_correlator import correlate_events
from services.storage import get_events, update_incident_status


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/analyze")
async def analyze_incident(payload: AnalyzeRequest):
    try:
        queue = progress_queues.setdefault(payload.incident_id, asyncio.Queue())
        await queue.put({"step": "correlate", "status": "running", "detail": "Correlating incident events"})
        await update_incident_status(payload.incident_id, IncidentStatus.correlating)
        result = correlate_events(await get_events(payload.incident_id), payload.start_time, payload.end_time)
        await queue.put({"step": "correlate", "status": "done", "detail": f"Found {len(result.anomaly_clusters)} anomaly clusters"})
        return result.model_dump(mode="json")
    except Exception as exc:
        logger.exception("Analyze failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
