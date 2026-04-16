import logging

from fastapi import APIRouter, HTTPException

from models.schemas import AIRunRequest, IncidentStatus, RCAOutput
from services.ai_pipeline import run_pipeline
from services.report_generator import generate_pdf
from services.storage import get_events, save_rca, save_report, update_incident_status


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/ai/run")
async def run_ai_pipeline(payload: AIRunRequest):
    try:
        await update_incident_status(payload.incident_id, IncidentStatus.analyzing)
        events = [event.model_dump(mode="json") for event in await get_events(payload.incident_id)]
        state = await run_pipeline(payload.incident_id, payload.readme, events)
        if state["error"]:
            await update_incident_status(payload.incident_id, IncidentStatus.error)
            raise HTTPException(status_code=500, detail=state["error"])
        rca = RCAOutput.model_validate(state["rca"])
        pdf_path = generate_pdf(payload.incident_id, rca, events, state["report_md"])
        await save_rca(payload.incident_id, rca)
        await save_report(payload.incident_id, state["report_md"], pdf_path)
        await update_incident_status(payload.incident_id, IncidentStatus.complete)
        return {"incident_id": payload.incident_id, "progress": state["progress"], "report_path": pdf_path}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("AI pipeline failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
