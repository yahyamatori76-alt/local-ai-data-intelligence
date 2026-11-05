"""Parse supported dataset formats and validate normalized records."""

import io
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd

from app.analytics.normalization import normalize_column_name, normalize_timestamp
from app.ingestion.log_parser import parse_json_lines

MAX_RECORDS = 100_000
SENSITIVE_COLUMN_PATTERN = re.compile(
    r"(^|_)(address|email|full_?name|name|nik|national_?id|"
    r"identity_?number|phone|phone_?number|social_?security_?number)(_|$)"
)


@dataclass(frozen=True)
class ValidatedRecord:
    row_number: int
    data: dict[str, Any]


@dataclass(frozen=True)
class ValidationResult:
    records: list[ValidatedRecord]
    rejections: list[tuple[int, str]]
    records_read: int


def parse_file(filename: str, content: bytes) -> list[dict[str, Any]]:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        if extension == "csv":
            frame = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
            rows = frame.to_dict(orient="records")
        elif extension == "xlsx":
            frame = pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False)
            rows = frame.to_dict(orient="records")
        elif extension == "json":
            parsed = json.loads(content.decode("utf-8-sig"))
            if isinstance(parsed, dict):
                parsed = parsed.get("records", [parsed])
            if not isinstance(parsed, list) or not all(
                isinstance(item, dict) for item in parsed
            ):
                raise ValueError("JSON file must contain an object or list of objects.")
            rows = parsed
        elif extension == "log":
            rows = parse_json_lines(content)
        else:
            raise ValueError("Unsupported file extension.")
    except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError("File could not be parsed; verify its format and encoding.") from exc

    if len(rows) > MAX_RECORDS:
        raise ValueError(f"File exceeds the {MAX_RECORDS} row processing limit.")
    if not rows:
        raise ValueError("File contains no records.")

    normalized_rows = []
    for row in rows:
        normalized: dict[str, Any] = {}
        for key, value in row.items():
            column = normalize_column_name(key)
            if not column:
                continue
            if column in normalized:
                raise ValueError("File contains duplicate column names after normalization.")
            normalized[column] = value
        normalized_rows.append(normalized)
    return normalized_rows


def validate_rows(
    source_type: str, rows: list[dict[str, Any]]
) -> ValidationResult:
    if source_type == "population":
        required = {"record_ref"}
    elif source_type == "marketplace":
        required = {"transaction_ref", "event_time", "authorized_join_ref"}
    elif source_type == "system_log":
        required = {"event_time", "event_ref", "authorized_join_ref"}
    else:
        raise ValueError("This source type is not enabled for file imports.")

    missing = required - set(rows[0])
    if missing:
        raise ValueError("Required columns are missing: " + ", ".join(sorted(missing)))
    columns = {column for row in rows for column in row}
    if any(SENSITIVE_COLUMN_PATTERN.search(column) for column in columns):
        raise ValueError(
            "Remove raw personal identifiers from the file; use approved masked references."
        )

    valid: list[ValidatedRecord] = []
    rejected: list[tuple[int, str]] = []
    seen_refs: set[str] = set()
    for row_number, row in enumerate(rows, start=1):
        try:
            if required - set(row):
                raise ValueError("missing_required_field")
            data = _normalize_record(source_type, row)
            reference = data.get(
                "transaction_ref", data.get("event_ref", data.get("record_ref"))
            )
            if reference in seen_refs:
                raise ValueError("duplicate_record_ref")
            seen_refs.add(reference)
            valid.append(ValidatedRecord(row_number=row_number, data=data))
        except ValueError as exc:
            rejected.append((row_number, str(exc)))
    return ValidationResult(valid, rejected, len(rows))


def _normalize_record(source_type: str, row: dict[str, Any]) -> dict[str, Any]:
    if source_type == "population":
        record_ref = _required_text(row, "record_ref", 128)
        masked_ref = _optional_text(row.get("masked_identity_ref"), 128)
        region_code = _optional_text(row.get("region_code"), 30)
        attributes = _attributes(
            row, {"record_ref", "masked_identity_ref", "region_code"}
        )
        return {
            "record_ref": record_ref,
            "masked_identity_ref": masked_ref,
            "region_code": region_code,
            "attributes": attributes,
        }

    event_time = normalize_timestamp(row.get("event_time"))
    if event_time is None:
        raise ValueError("invalid_timestamp")
    join_ref = _required_text(row, "authorized_join_ref", 128)

    if source_type == "marketplace":
        transaction_ref = _required_text(row, "transaction_ref", 128)
        amount_value = row.get("amount")
        amount = None
        if amount_value not in (None, ""):
            try:
                amount = Decimal(str(amount_value))
            except InvalidOperation as exc:
                raise ValueError("invalid_amount") from exc
            if not amount.is_finite() or amount < 0:
                raise ValueError("invalid_amount")
        return {
            "transaction_ref": transaction_ref,
            "event_time": event_time,
            "status": _optional_text(row.get("status"), 40),
            "amount": amount,
            "currency": (_optional_text(row.get("currency"), 3) or "IDR").upper(),
            "authorized_join_ref": join_ref,
            "attributes": _attributes(
                row,
                {
                    "transaction_ref",
                    "event_time",
                    "status",
                    "amount",
                    "currency",
                    "authorized_join_ref",
                },
            ),
        }

    return {
        "event_time": event_time,
        "severity": _optional_text(row.get("severity"), 20),
        "event_type": _optional_text(row.get("event_type"), 100),
        "event_ref": _required_text(row, "event_ref", 128),
        "authorized_join_ref": join_ref,
        "message": _optional_text(row.get("message"), 2000),
        "attributes": _attributes(
            row,
            {
                "event_time",
                "severity",
                "event_type",
                "event_ref",
                "authorized_join_ref",
                "message",
            },
        ),
    }


def _required_text(row: dict[str, Any], key: str, max_length: int) -> str:
    value = _optional_text(row.get(key), max_length)
    if not value:
        raise ValueError("missing_required_field")
    return value


def _optional_text(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    if not result:
        return None
    if len(result) > max_length:
        raise ValueError("field_too_long")
    return result


def _attributes(row: dict[str, Any], excluded: set[str]) -> dict[str, Any]:
    return {
        key: str(value)
        for key, value in row.items()
        if key not in excluded and value not in (None, "")
    }
