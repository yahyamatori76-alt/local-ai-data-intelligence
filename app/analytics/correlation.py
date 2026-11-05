"""Deterministic correlation using an approved reference and time window."""

from datetime import datetime
from typing import Any


def correlate_records(
    transactions: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    time_window_seconds: int,
) -> list[tuple[dict[str, Any], dict[str, Any], float]]:
    events_by_reference: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        reference = event.get("authorized_join_ref")
        if reference:
            events_by_reference.setdefault(reference, []).append(event)

    matches = []
    for transaction in transactions:
        reference = transaction.get("authorized_join_ref")
        event_time = transaction.get("event_time")
        if not reference or not isinstance(event_time, datetime):
            continue
        for event in events_by_reference.get(reference, []):
            other_time = event.get("event_time")
            if not isinstance(other_time, datetime):
                continue
            difference = abs((event_time - other_time).total_seconds())
            if difference <= time_window_seconds:
                matches.append((transaction, event, difference))
    return matches
