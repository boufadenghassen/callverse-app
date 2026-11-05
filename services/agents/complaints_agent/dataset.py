"""Optional external complaint dataset support.

The application keeps its operational SQLite store unchanged. Setting
COMPLAINTS_CSV enables a read-only dataset summary for analysis and demos.
"""
import csv
import datetime as dt
import os
from collections import Counter
from pathlib import Path

from . import classifier


def path() -> Path | None:
    value = os.environ.get("COMPLAINTS_CSV")
    return Path(value) if value else None


def _date(value: str) -> dt.datetime | None:
    for fmt in ("%d-%m-%y", "%m-%d-%y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def rows() -> list[dict]:
    source = path()
    if source is None or not source.is_file():
        return []
    with source.open(newline="", encoding="utf-8-sig") as handle:
        out = []
        for row in csv.DictReader(handle):
            text = (row.get("Customer Complaint") or "").strip()
            if not text:
                continue
            result = classifier.classify(text)
            out.append({
                "id": (row.get("Ticket #") or "").strip(),
                "text": text,
                "status": (row.get("Status") or "").strip(),
                "channel": (row.get("Received Via") or "").strip(),
                "city": (row.get("City") or "").strip(),
                "state": (row.get("State") or "").strip(),
                "openedAt": _date(row.get("Date") or ""),
                "cluster": result["key"],
                "similarity": result["similarity"],
                "method": result["method"],
            })
        return out


def overview() -> dict:
    source = path()
    records = rows()
    counts = Counter(record["cluster"] for record in records)
    open_statuses = {"open", "pending"}
    return {
        "enabled": source is not None,
        "path": str(source) if source else None,
        "records": len(records),
        "open": sum(record["status"].lower() in open_statuses for record in records),
        "clusters": [{"key": key, "count": count} for key, count in counts.most_common()],
        "methods": dict(Counter(record["method"] for record in records)),
        "note": "Unlabelled external data is descriptive only; it is not used as ground truth for model evaluation.",
    }
