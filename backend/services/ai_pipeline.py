import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from models.schemas import ProgressEvent, RCAOutput
from services.ai_provider import get_provider


PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
progress_queues: dict[str, asyncio.Queue[dict]] = {}


class PipelineState(TypedDict):
    incident_id: str
    readme: str
    events: list[dict]
    summaries: dict
    rca: dict
    report_md: str
    progress: list[dict]
    error: str | None


def _prompt(name: str, **kwargs: str) -> str:
    template = (PROMPT_DIR / name).read_text(encoding="utf-8")
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", value)
    return template


def _parse_event_timestamp(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _event_time_bounds(events: list[dict]) -> tuple[datetime, datetime]:
    timestamps = [
        parsed
        for parsed in (_parse_event_timestamp(event.get("timestamp")) for event in events)
        if parsed is not None
    ]
    now = datetime.now(timezone.utc)
    if not timestamps:
        return now, now
    return min(timestamps), max(timestamps)


def _normalize_rca_payload(payload: dict, events: list[dict]) -> dict:
    fallback_start, fallback_end = _event_time_bounds(events)

    def normalize_timestamp(raw_value: object, fallback: datetime) -> str:
        if isinstance(raw_value, str):
            parsed = _parse_event_timestamp(raw_value)
            if parsed is not None:
                return parsed.isoformat()
        return fallback.isoformat()

    normalized = dict(payload)
    normalized["first_anomaly_timestamp"] = normalize_timestamp(
        normalized.get("first_anomaly_timestamp"),
        fallback_start,
    )
    normalized["resolution_timestamp"] = normalize_timestamp(
        normalized.get("resolution_timestamp"),
        fallback_end,
    )
    return normalized


async def _push(state: PipelineState, step: str, status: str, detail: str) -> None:
    event = ProgressEvent(step=step, status=status, detail=detail).model_dump(mode="json")
    state["progress"].append(event)
    await progress_queues.setdefault(state["incident_id"], asyncio.Queue()).put(event)


async def summarize_errors(state: PipelineState) -> PipelineState:
    await _push(state, "summarize", "running", f"Summarizing {len(state['events'])} correlated events")
    prompt = _prompt("summarize_errors.txt", events_json=json.dumps(state["events"], indent=2))
    state["summaries"] = json.loads(await get_provider().complete(prompt))
    await _push(state, "summarize", "done", "Service summaries created")
    return state


async def root_cause_analysis(state: PipelineState) -> PipelineState:
    await _push(state, "rca", "running", "Performing root cause analysis")
    prompt = _prompt("root_cause_analysis.txt", summaries_json=json.dumps(state["summaries"], indent=2), readme=state["readme"] or "No additional context provided.")
    raw_payload = json.loads(await get_provider().complete(prompt))
    state["rca"] = RCAOutput.model_validate(
        _normalize_rca_payload(raw_payload, state["events"])
    ).model_dump(mode="json")
    await _push(state, "rca", "done", "RCA completed")
    return state


async def write_postmortem(state: PipelineState) -> PipelineState:
    await _push(state, "report", "running", "Writing post-mortem report")
    prompt = _prompt("postmortem_report.txt", rca_json=json.dumps(state["rca"], indent=2), events_json=json.dumps(state["events"][:30], indent=2))
    state["report_md"] = await get_provider().complete(prompt)
    await _push(state, "report", "done", "Markdown post-mortem created")
    return state


graph = StateGraph(PipelineState)
graph.add_node("summarize_node", summarize_errors)
graph.add_node("rca_node", root_cause_analysis)
graph.add_node("postmortem_node", write_postmortem)
graph.add_edge(START, "summarize_node")
graph.add_edge("summarize_node", "rca_node")
graph.add_edge("rca_node", "postmortem_node")
graph.add_edge("postmortem_node", END)
app = graph.compile()


async def run_pipeline(incident_id: str, readme: str, events: list[dict]) -> PipelineState:
    progress_queues[incident_id] = asyncio.Queue()
    state: PipelineState = {"incident_id": incident_id, "readme": readme, "events": events, "summaries": {}, "rca": {}, "report_md": "", "progress": [], "error": None}
    try:
        return await app.ainvoke(state)
    except Exception as exc:
        state["error"] = str(exc)
        await _push(state, "report", "error", str(exc))
        return state
