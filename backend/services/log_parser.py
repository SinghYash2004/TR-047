import json
import logging
import re
from datetime import datetime, timezone

from models.schemas import LogEvent, LogLevel


logger = logging.getLogger(__name__)
SYSLOG_RE = re.compile(r"^(\w{3}\s+\d{1,2}\s+[\d:]+)\s+\S+\s+(\S+?)\[?\d*\]?:\s+(.+)$")
ACCESS_RE = re.compile(r'^(\S+) \S+ \S+ \[(.+?)\] "(\S+ \S+ \S+)" (\d{3}) (\d+)')
APP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T[\d:]+Z?)\s+(ERROR|WARN|INFO|DEBUG)\s+\[([^\]]+)\]\s+(.+)$")


def _to_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _infer_level(message: str) -> LogLevel:
    lowered = message.lower()
    if "error" in lowered or "exception" in lowered or "timeout" in lowered:
        return LogLevel.ERROR
    if "warn" in lowered or "degraded" in lowered:
        return LogLevel.WARN
    return LogLevel.INFO


def _service_from_filename(source_file: str) -> str:
    name = source_file.lower()
    if "nginx" in name or "server" in name:
        return "nginx"
    if "apache" in name:
        return "apache"
    return source_file.rsplit(".", 1)[0]


def parse_lines(lines: list[str], source_file: str) -> list[LogEvent]:
    events: list[LogEvent] = []
    current_year = 2025
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            if match := SYSLOG_RE.match(line):
                stamp, service, message = match.groups()
                ts = _to_utc(datetime.strptime(f"{current_year} {stamp}", "%Y %b %d %H:%M:%S"))
                events.append(LogEvent(timestamp=ts, source_file=source_file, service=service, level=_infer_level(message), message=message))
                continue
            if match := ACCESS_RE.match(line):
                ip, stamp, request, status, size = match.groups()
                ts = _to_utc(datetime.strptime(stamp, "%d/%b/%Y:%H:%M:%S %z"))
                code = int(status)
                level = LogLevel.ERROR if code >= 500 else LogLevel.WARN if code >= 400 else LogLevel.INFO
                events.append(LogEvent(timestamp=ts, source_file=source_file, service=_service_from_filename(source_file), level=level, message=f"{request} -> {status}", parsed_fields={"ip": ip, "status": code, "bytes": int(size)}))
                continue
            if match := APP_RE.match(line):
                stamp, level, service, message = match.groups()
                ts = _to_utc(datetime.fromisoformat((stamp if stamp.endswith("Z") else f"{stamp}Z").replace("Z", "+00:00")))
                events.append(LogEvent(timestamp=ts, source_file=source_file, service=service, level=LogLevel(level), message=message))
                continue
            if line.startswith("{"):
                obj = json.loads(line)
                ts = _to_utc(datetime.fromisoformat(str(obj["timestamp"]).replace("Z", "+00:00")))
                parsed = {k: v for k, v in obj.items() if k not in {"timestamp", "service", "level", "message"}}
                events.append(LogEvent(timestamp=ts, source_file=source_file, service=str(obj["service"]), level=LogLevel(str(obj["level"]).upper()), message=str(obj["message"]), parsed_fields=parsed))
                continue
        except Exception as exc:
            logger.warning("Failed to parse line from %s: %s", source_file, exc)
            continue
        logger.warning("Unparsed line in %s: %s", source_file, line)
    return events


def parse_text(content: str, source_file: str) -> list[LogEvent]:
    return parse_lines(content.splitlines(), source_file)
