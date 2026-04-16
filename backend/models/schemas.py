from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class BaseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class LogLevel(str, Enum):
    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"
    DEBUG = "DEBUG"


class ImpactLevel(str, Enum):
    HIGH = "HIGH"
    MED = "MED"
    LOW = "LOW"


class IncidentStatus(str, Enum):
    uploading = "uploading"
    parsing = "parsing"
    correlating = "correlating"
    analyzing = "analyzing"
    complete = "complete"
    error = "error"


class LogEvent(BaseSchema):
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime
    source_file: str
    service: str
    level: LogLevel
    message: str
    parsed_fields: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalize(self) -> "LogEvent":
        self.timestamp = ensure_utc(self.timestamp)
        return self


class EvidenceItem(BaseSchema):
    timestamp: datetime
    service: str
    log_line: str
    significance: str

    @model_validator(mode="after")
    def _normalize(self) -> "EvidenceItem":
        self.timestamp = ensure_utc(self.timestamp)
        return self


class AffectedService(BaseSchema):
    service: str
    impact_level: ImpactLevel
    error_count: int


class RCAOutput(BaseSchema):
    root_cause: str
    confidence: float
    confidence_reasoning: str
    evidence: list[EvidenceItem]
    cascade_chain: list[str]
    affected_services: list[AffectedService]
    estimated_downtime_minutes: int
    first_anomaly_timestamp: datetime
    resolution_timestamp: datetime

    @model_validator(mode="after")
    def _normalize(self) -> "RCAOutput":
        self.first_anomaly_timestamp = ensure_utc(self.first_anomaly_timestamp)
        self.resolution_timestamp = ensure_utc(self.resolution_timestamp)
        self.confidence = max(0.0, min(1.0, self.confidence))
        return self


class IncidentSummary(BaseSchema):
    incident_id: str
    status: IncidentStatus
    total_events: int
    error_count: int
    warn_count: int
    duration_minutes: int
    affected_services: list[str]
    created_at: datetime

    @model_validator(mode="after")
    def _normalize(self) -> "IncidentSummary":
        self.created_at = ensure_utc(self.created_at)
        return self


class ProgressEvent(BaseSchema):
    step: str
    status: str
    detail: str


class AnalyzeRequest(BaseSchema):
    incident_id: str
    start_time: datetime
    end_time: datetime
    context: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "AnalyzeRequest":
        self.start_time = ensure_utc(self.start_time)
        self.end_time = ensure_utc(self.end_time)
        return self


class AIRunRequest(BaseSchema):
    incident_id: str
    readme: str = ""
