from datetime import datetime, timedelta, timezone

from app.analytics.correlation import correlate_records


BASE = datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc)


def test_correlation_matches_authorized_reference_within_window():
    transactions = [
        {
            "transaction_ref": "TX-1",
            "authorized_join_ref": "SESSION-1",
            "event_time": BASE,
        }
    ]
    events = [
        {
            "event_ref": "EV-1",
            "authorized_join_ref": "SESSION-1",
            "event_time": BASE + timedelta(seconds=300),
        }
    ]

    matches = correlate_records(
        transactions, events, time_window_seconds=300
    )

    assert len(matches) == 1
    assert matches[0][2] == 300


def test_correlation_excludes_outside_window_and_missing_reference():
    transactions = [
        {
            "transaction_ref": "TX-1",
            "authorized_join_ref": "SESSION-1",
            "event_time": BASE,
        },
        {
            "transaction_ref": "TX-2",
            "authorized_join_ref": None,
            "event_time": BASE,
        },
    ]
    events = [
        {
            "event_ref": "EV-1",
            "authorized_join_ref": "SESSION-1",
            "event_time": BASE + timedelta(seconds=301),
        }
    ]

    assert correlate_records(
        transactions, events, time_window_seconds=300
    ) == []
