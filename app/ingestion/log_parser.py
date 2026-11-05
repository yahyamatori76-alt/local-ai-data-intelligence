"""Parse JSON Lines system logs into event records."""

import json
from typing import Any


def parse_json_lines(data: bytes) -> list[dict[str, Any]]:
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Log file must use UTF-8 encoding.") from exc

    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON log record at line {line_number}."
            ) from exc
        if not isinstance(record, dict):
            raise ValueError(f"Log record at line {line_number} must be an object.")
        records.append(record)
    return records
