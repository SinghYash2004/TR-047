from services.log_parser import parse_text


def test_parse_syslog():
    events = parse_text("Aug 15 10:05:10 host authsvc[123]: database error detected", "sys.log")
    assert len(events) >= 1


def test_parse_apache():
    events = parse_text('127.0.0.1 - - [15/Mar/2025:02:14:00 +0000] "GET /login HTTP/1.1" 503 512', "server.log")
    assert events[0].level.value == "ERROR"


def test_parse_app_log():
    events = parse_text("2025-03-15T02:14:00Z ERROR [AuthService] database timeout", "app.log")
    assert events[0].service == "AuthService"


def test_parse_json_log():
    events = parse_text('{"timestamp":"2025-03-15T02:14:00Z","level":"ERROR","service":"db","message":"pool exhausted","pool_size":50}', "db.log")
    assert events[0].parsed_fields["pool_size"] == 50


def test_parse_mixed_file():
    mixed = "\n".join([
        "Aug 15 10:05:10 host authsvc[123]: warning threshold reached",
        '127.0.0.1 - - [15/Mar/2025:02:14:00 +0000] "GET /login HTTP/1.1" 200 512',
        "2025-03-15T02:14:00Z INFO [AuthService] request accepted",
        '{"timestamp":"2025-03-15T02:14:00Z","level":"ERROR","service":"db","message":"pool exhausted"}',
    ])
    assert len(parse_text(mixed, "mixed.log")) == 4
