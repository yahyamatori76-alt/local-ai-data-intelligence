import pytest

from app.analytics.normalization import normalize_column_name, normalize_timestamp
from app.ingestion.validation import parse_file, validate_rows


def test_marketplace_rows_validate_and_normalize_to_utc():
    rows = parse_file(
        "transactions.csv",
        b"Transaction Ref,Event Time,Authorized Join Ref\n"
        b"TX-1,2026-11-01T10:15:00+07:00,SESSION-1\n",
    )

    result = validate_rows("marketplace", rows)

    assert result.records_read == 1
    assert not result.rejections
    assert result.records[0].data["transaction_ref"] == "TX-1"
    assert result.records[0].data["event_time"].isoformat() == (
        "2026-11-01T03:15:00+00:00"
    )


def test_missing_required_column_is_rejected():
    rows = parse_file("transactions.json", b'[{"transaction_ref":"TX-1"}]')

    with pytest.raises(ValueError, match="Required columns are missing"):
        validate_rows("marketplace", rows)


def test_invalid_timestamp_is_recorded_as_non_sensitive_reason():
    result = validate_rows(
        "marketplace",
        [
            {
                "transaction_ref": "TX-1",
                "event_time": "not-a-time",
                "authorized_join_ref": "SESSION-1",
            }
        ],
    )

    assert result.records == []
    assert result.rejections == [(1, "invalid_timestamp")]


def test_duplicate_records_are_rejected():
    result = validate_rows(
        "marketplace",
        [
            {
                "transaction_ref": "TX-1",
                "event_time": "2026-11-01T10:00:00Z",
                "authorized_join_ref": "SESSION-1",
            },
            {
                "transaction_ref": "TX-1",
                "event_time": "2026-11-01T10:00:01Z",
                "authorized_join_ref": "SESSION-1",
            },
        ],
    )

    assert len(result.records) == 1
    assert result.rejections == [(2, "duplicate_record_ref")]


def test_raw_personal_columns_are_rejected():
    with pytest.raises(ValueError, match="raw personal identifiers"):
        validate_rows(
            "marketplace",
            [
                {
                    "transaction_ref": "TX-1",
                    "event_time": "2026-11-01T10:00:00Z",
                    "authorized_join_ref": "SESSION-1",
                    "email": "person@example.test",
                }
            ],
        )


def test_raw_personal_columns_in_later_json_rows_are_rejected():
    with pytest.raises(ValueError, match="raw personal identifiers"):
        validate_rows(
            "marketplace",
            [
                {
                    "transaction_ref": "TX-1",
                    "event_time": "2026-11-01T10:00:00Z",
                    "authorized_join_ref": "SESSION-1",
                },
                {
                    "transaction_ref": "TX-2",
                    "event_time": "2026-11-01T10:00:00Z",
                    "authorized_join_ref": "SESSION-2",
                    "email": "person@example.test",
                },
            ],
        )


def test_normalization_helpers():
    assert normalize_column_name("Event Time") == "event_time"
    assert normalize_timestamp("invalid") is None


def test_json_lines_parser():
    rows = parse_file(
        "events.log",
        b'{"event_time":"2026-11-01T10:00:00Z","event_ref":"EV-1",'
        b'"authorized_join_ref":"SESSION-1"}\n',
    )

    assert rows[0]["event_ref"] == "EV-1"


def test_unsupported_file_extension_is_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        parse_file("records.exe", b"")
