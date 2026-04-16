import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select

from models.database import IncidentORM, LogEventORM, RCAResultORM, ReportORM, get_session
from models.schemas import IncidentStatus, IncidentSummary, LogEvent, RCAOutput


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _summary_from_orm(incident: IncidentORM, events: list[LogEvent]) -> IncidentSummary:
    start = datetime.fromisoformat((incident.start_time or utc_now().isoformat()).replace("Z", "+00:00"))
    end = datetime.fromisoformat((incident.end_time or start.isoformat()).replace("Z", "+00:00"))
    return IncidentSummary(
        incident_id=incident.id,
        status=IncidentStatus(incident.status),
        total_events=len(events),
        error_count=sum(event.level.value == "ERROR" for event in events),
        warn_count=sum(event.level.value == "WARN" for event in events),
        duration_minutes=max(0, int((end - start).total_seconds() // 60)),
        affected_services=sorted({event.service for event in events}),
        created_at=datetime.fromisoformat(incident.created_at.replace("Z", "+00:00")),
    )


async def create_incident(start_time: datetime, end_time: datetime, readme: str) -> str:
    incident_id = str(uuid4())
    async with get_session() as session:
        session.add(IncidentORM(id=incident_id, status=IncidentStatus.uploading.value, readme=readme, start_time=start_time.isoformat(), end_time=end_time.isoformat(), created_at=utc_now().isoformat()))
        await session.commit()
    return incident_id


async def update_incident_status(incident_id: str, status: IncidentStatus) -> None:
    async with get_session() as session:
        incident = await session.get(IncidentORM, incident_id)
        if incident:
            incident.status = status.value
            await session.commit()


async def store_events(incident_id: str, events: list[LogEvent]) -> None:
    async with get_session() as session:
        await session.execute(delete(LogEventORM).where(LogEventORM.incident_id == incident_id))
        session.add_all([LogEventORM(id=event.id, incident_id=incident_id, timestamp=event.timestamp.isoformat(), source_file=event.source_file, service=event.service, level=event.level.value, message=event.message, parsed_fields=json.dumps(event.parsed_fields)) for event in events])
        await session.commit()


async def get_events(incident_id: str) -> list[LogEvent]:
    async with get_session() as session:
        rows = (await session.execute(select(LogEventORM).where(LogEventORM.incident_id == incident_id).order_by(LogEventORM.timestamp.asc()))).scalars().all()
    return [LogEvent(id=row.id, timestamp=datetime.fromisoformat(row.timestamp.replace("Z", "+00:00")), source_file=row.source_file or "", service=row.service or "", level=row.level or "INFO", message=row.message or "", parsed_fields=json.loads(row.parsed_fields or "{}")) for row in rows]


async def list_incidents() -> list[IncidentSummary]:
    async with get_session() as session:
        incidents = (await session.execute(select(IncidentORM).order_by(IncidentORM.created_at.desc()))).scalars().all()
    return [_summary_from_orm(incident, await get_events(incident.id)) for incident in incidents]


async def get_incident_summary(incident_id: str) -> IncidentSummary | None:
    async with get_session() as session:
        incident = await session.get(IncidentORM, incident_id)
    return None if incident is None else _summary_from_orm(incident, await get_events(incident_id))


async def get_incident_record(incident_id: str) -> IncidentORM | None:
    async with get_session() as session:
        return await session.get(IncidentORM, incident_id)


async def save_rca(incident_id: str, rca: RCAOutput) -> None:
    async with get_session() as session:
        payload = json.dumps(rca.model_dump(mode="json"))
        existing = (await session.execute(select(RCAResultORM).where(RCAResultORM.incident_id == incident_id))).scalar_one_or_none()
        if existing:
            existing.rca_json = payload
        else:
            session.add(RCAResultORM(id=str(uuid4()), incident_id=incident_id, rca_json=payload, created_at=utc_now().isoformat()))
        await session.commit()


async def get_rca(incident_id: str) -> RCAOutput | None:
    async with get_session() as session:
        row = (await session.execute(select(RCAResultORM).where(RCAResultORM.incident_id == incident_id))).scalar_one_or_none()
    return None if row is None else RCAOutput.model_validate(json.loads(row.rca_json))


async def save_report(incident_id: str, markdown: str, pdf_path: str) -> None:
    async with get_session() as session:
        existing = (await session.execute(select(ReportORM).where(ReportORM.incident_id == incident_id))).scalar_one_or_none()
        if existing:
            existing.markdown = markdown
            existing.pdf_path = pdf_path
        else:
            session.add(ReportORM(id=str(uuid4()), incident_id=incident_id, markdown=markdown, pdf_path=pdf_path, created_at=utc_now().isoformat()))
        await session.commit()


async def get_report(incident_id: str) -> ReportORM | None:
    async with get_session() as session:
        return (await session.execute(select(ReportORM).where(ReportORM.incident_id == incident_id))).scalar_one_or_none()
