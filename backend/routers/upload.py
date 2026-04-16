import asyncio
import logging
from typing import Annotated
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from models.schemas import IncidentStatus
from services.ai_pipeline import progress_queues
from services.log_parser import parse_text
from services.storage import create_incident, get_incident_summary, store_events, update_incident_status


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/upload")
async def upload_logs(
    logs: Annotated[list[UploadFile], File()],
    incident_start: Annotated[str, Form()],
    incident_end: Annotated[str, Form()],
    readme: Annotated[str, Form()] = "",
):
    try:
        start = datetime.fromisoformat(incident_start.replace("Z", "+00:00"))
        end = datetime.fromisoformat(incident_end.replace("Z", "+00:00"))
        incident_id = await create_incident(start, end, readme)
        queue = progress_queues.setdefault(incident_id, asyncio.Queue())
        await queue.put({"step": "parse", "status": "running", "detail": f"Parsing {len(logs)} files"})
        await update_incident_status(incident_id, IncidentStatus.parsing)
        events = []
        for log in logs:
            events.extend(parse_text((await log.read()).decode("utf-8", errors="ignore"), log.filename or "unknown.log"))
        await store_events(incident_id, events)
        await queue.put({"step": "parse", "status": "done", "detail": f"Parsed {len(events)} events"})
        return await get_incident_summary(incident_id)
    except Exception as exc:
        logger.exception("Upload failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
