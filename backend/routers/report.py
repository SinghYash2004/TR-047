import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse

from models.schemas import IncidentStatus, RCAOutput
from services.ai_pipeline import progress_queues, run_pipeline
from services.event_correlator import correlate_events
from services.log_parser import parse_text
from services.report_generator import generate_pdf
from services.storage import get_events, get_incident_summary, get_rca, get_report, list_incidents
from services.storage import create_incident, save_rca, save_report, store_events, update_incident_status


router = APIRouter()
logger = logging.getLogger(__name__)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _severity_from_rca(rca: RCAOutput) -> str:
    rank = {"HIGH": 3, "MED": 2, "LOW": 1}
    highest = max((service.impact_level.value for service in rca.affected_services), key=lambda value: rank[value], default="LOW")
    return {"HIGH": "SEV-1", "MED": "SEV-2", "LOW": "SEV-3"}[highest]


def _extract_summary(markdown: str) -> str:
    if "## Incident Timeline" not in markdown:
        return markdown.strip()
    return markdown.split("## Incident Timeline", 1)[0].replace("## Summary", "", 1).strip()


def _extract_action_items(markdown: str) -> list[str]:
    actions: list[str] = []
    in_actions = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_actions = stripped == "## Preventive Actions"
            continue
        if in_actions and stripped.startswith("- "):
            actions.append(stripped.removeprefix("- ").strip())
    return actions


def _build_timeline(rca: RCAOutput) -> list[dict[str, str]]:
    timeline = []
    for item in rca.evidence:
        timeline.append(
            {
                "time": item.timestamp.isoformat(),
                "title": f"{item.service} event",
                "detail": item.log_line,
                "source": item.significance,
            }
        )
    return timeline


@router.post("/api/incidents/report")
async def generate_incident_report(
    files: Annotated[list[UploadFile], File()],
    start_timestamp: Annotated[str, Form()],
    end_timestamp: Annotated[str, Form()],
    architecture_context: Annotated[str, Form()] = "",
):
    try:
        start = _parse_timestamp(start_timestamp)
        end = _parse_timestamp(end_timestamp)
        incident_id = await create_incident(start, end, architecture_context)
        await update_incident_status(incident_id, IncidentStatus.parsing)

        parsed_events = []
        for file in files:
            content = (await file.read()).decode("utf-8", errors="ignore")
            parsed_events.extend(parse_text(content, file.filename or "unknown.log"))
        await store_events(incident_id, parsed_events)

        correlation = correlate_events(parsed_events, start, end)
        await update_incident_status(incident_id, IncidentStatus.analyzing)
        state = await run_pipeline(
            incident_id,
            architecture_context,
            [event.model_dump(mode="json") for event in correlation.filtered_events],
        )
        if state["error"]:
            await update_incident_status(incident_id, IncidentStatus.error)
            raise HTTPException(status_code=500, detail=state["error"])

        rca = RCAOutput.model_validate(state["rca"])
        report_markdown = state["report_md"]
        pdf_path = generate_pdf(
            incident_id,
            rca,
            [event.model_dump(mode="json") for event in correlation.filtered_events],
            report_markdown,
        )
        await save_rca(incident_id, rca)
        await save_report(incident_id, report_markdown, pdf_path)
        await update_incident_status(incident_id, IncidentStatus.complete)

        return {
            "incident_id": incident_id,
            "incident_window": {
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
            "timeline": _build_timeline(rca),
            "root_cause": rca.root_cause,
            "confidence": rca.confidence,
            "impact": {
                "affected_services": [service.service for service in rca.affected_services],
                "estimated_downtime": f"{rca.estimated_downtime_minutes} minutes",
                "severity": _severity_from_rca(rca),
            },
            "postmortem": {
                "summary": _extract_summary(report_markdown),
                "timeline_summary": " -> ".join(rca.cascade_chain) if rca.cascade_chain else "No cascade chain detected.",
                "rca": rca.confidence_reasoning,
                "action_items": _extract_action_items(report_markdown),
            },
            "source_count": len(files),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Report generation failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/incidents")
async def incidents():
    return [item.model_dump(mode="json") for item in await list_incidents()]


@router.get("/incidents/{incident_id}")
async def incident_summary(incident_id: str):
    summary = await get_incident_summary(incident_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return summary.model_dump(mode="json")


@router.get("/incidents/{incident_id}/events")
async def incident_events(incident_id: str):
    return [event.model_dump(mode="json") for event in await get_events(incident_id)]


@router.get("/incidents/{incident_id}/rca")
async def incident_rca(incident_id: str):
    rca = await get_rca(incident_id)
    if rca is None:
        raise HTTPException(status_code=404, detail="RCA not found")
    return rca.model_dump(mode="json")


@router.get("/incidents/{incident_id}/report/md")
async def incident_markdown(incident_id: str):
    report = await get_report(incident_id)
    if report is None or not report.markdown:
        raise HTTPException(status_code=404, detail="Report not found")
    return PlainTextResponse(report.markdown)


@router.get("/incidents/{incident_id}/report/pdf")
async def incident_pdf(incident_id: str):
    report = await get_report(incident_id)
    if report is None or not report.pdf_path or not Path(report.pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(report.pdf_path, media_type="application/pdf", filename=f"{incident_id}.pdf")


@router.get("/incidents/{incident_id}/progress")
async def incident_progress(incident_id: str):
    queue = progress_queues.setdefault(incident_id, asyncio.Queue())

    async def stream():
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=30)
                yield f"data: {json.dumps(item)}\n\n"
                if item["step"] == "report" and item["status"] in {"done", "error"}:
                    break
            except asyncio.TimeoutError:
                yield ": ping\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
