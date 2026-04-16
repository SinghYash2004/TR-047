from collections import defaultdict
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict

from models.schemas import LogEvent, LogLevel


class ServiceStat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service: str
    total: int
    errors: int
    warnings: int


class AnomalyCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_time: datetime
    end_time: datetime
    service: str
    error_count: int
    events: list[str]


class CorrelationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filtered_events: list[LogEvent]
    anomaly_clusters: list[AnomalyCluster]
    cascade_chain: list[str]
    service_stats: dict[str, ServiceStat]


def correlate_events(events: list[LogEvent], start: datetime, end: datetime) -> CorrelationResult:
    filtered = sorted((e for e in events if start <= e.timestamp <= end), key=lambda e: e.timestamp)
    groups: dict[str, list[LogEvent]] = defaultdict(list)
    for event in filtered:
        groups[event.service].append(event)
    stats = {service: ServiceStat(service=service, total=len(items), errors=sum(i.level == LogLevel.ERROR for i in items), warnings=sum(i.level == LogLevel.WARN for i in items)) for service, items in groups.items()}
    clusters: list[AnomalyCluster] = []
    for service, items in groups.items():
        errors = [e for e in items if e.level == LogLevel.ERROR]
        left = 0
        for right, event in enumerate(errors):
            while errors[left].timestamp < event.timestamp - timedelta(seconds=60):
                left += 1
            window = errors[left : right + 1]
            if len(window) >= 5:
                cluster = AnomalyCluster(start_time=window[0].timestamp, end_time=window[-1].timestamp, service=service, error_count=len(window), events=[e.id for e in window])
                if not clusters or (clusters[-1].service, clusters[-1].start_time) != (cluster.service, cluster.start_time):
                    clusters.append(cluster)
    clusters.sort(key=lambda item: item.start_time)
    cascade: list[str] = []
    for first in clusters:
        for second in clusters:
            gap = second.start_time - first.end_time
            if first.service != second.service and timedelta(0) <= gap <= timedelta(seconds=30):
                link = f"{first.service} → {second.service}"
                if link not in cascade:
                    cascade.append(link)
    return CorrelationResult(filtered_events=filtered, anomaly_clusters=clusters, cascade_chain=cascade, service_stats=stats)
