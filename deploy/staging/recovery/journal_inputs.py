"""Validate the private identity and payload of an independent marker journal."""

import hashlib
import json
import re
from datetime import datetime

from reconcile import marker_rows, utc

MAX_EVENT_BYTES = 4096
EPOCH_PATTERN = r"[0-9a-f]{32}"
EVENT_KEYS = {
    "format",
    "schema_revision",
    "journal_epoch",
    "key_fingerprint",
    "captured_at",
    "deletions",
    "suppressions",
}


def prefix(epoch: str, *, drill: bool, production: bool = False) -> str:
    if not re.fullmatch(EPOCH_PATTERN, epoch):
        raise ValueError("Invalid recovery journal epoch.")
    if production:
        if drill:
            raise ValueError("Choose either a production or a rehearsal journal.")
        return f"markers/production/journal/{epoch}/"
    return ("markers/drills/journal/" if drill else "markers/journal/") + epoch + "/"


def check_identity(marker: dict, epoch: str, fingerprint: str) -> None:
    if (
        set(marker) != EVENT_KEYS
        or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
        or marker["journal_epoch"] != epoch
        or marker["key_fingerprint"] != fingerprint
        or not isinstance(marker["deletions"], list)
        or not isinstance(marker["suppressions"], list)
    ):
        raise ValueError("Recovery journal record does not match the epoch and application keys.")
    marker_rows(marker)


def canonical_event(raw: bytes, epoch: str, fingerprint: str) -> bytes:
    if len(raw) > MAX_EVENT_BYTES:
        raise ValueError("Oversized recovery journal record.")
    marker = json.loads(raw)
    check_identity(marker, epoch, fingerprint)
    deletions, suppressions = marker["deletions"], marker["suppressions"]
    if not (
        (len(deletions) == 1 and not suppressions)
        or (not deletions and 1 <= len(suppressions) <= 20)
    ):
        raise ValueError("A journal record must describe one authorized operation.")
    if any(row[-1] != marker["captured_at"] for row in deletions + suppressions):
        raise ValueError("Invalid recovery journal timestamp.")
    return (json.dumps(marker, separators=(",", ":"), sort_keys=True) + "\n").encode()


def name(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest() + ".json"


def merge(
    baseline: dict,
    objects: dict[str, bytes],
    epoch: str,
    fingerprint: str,
    fenced_at: datetime,
) -> dict:
    check_identity(baseline, epoch, fingerprint)
    baseline_at = utc(baseline["captured_at"])
    if baseline_at > fenced_at:
        raise ValueError("The verified source fence precedes the journal baseline.")
    deletions: dict[str, list[str]] = {}
    suppressions: dict[str, list[str]] = {}

    def add(marker: dict) -> None:
        for row in marker["deletions"]:
            user, digest, stamp = row
            previous = deletions.get(user)
            if previous is not None and previous[1] != digest:
                raise ValueError("Conflicting journal digests for the same account.")
            if previous is None or utc(stamp) < utc(previous[-1]):
                deletions[user] = row
        for row in marker["suppressions"]:
            digest, reason, stamp = row
            previous = suppressions.get(digest)
            if previous is None or (utc(stamp), reason) < (
                utc(previous[-1]),
                previous[1],
            ):
                suppressions[digest] = row

    add(baseline)
    for key, raw in sorted(objects.items()):
        normalized = canonical_event(raw, epoch, fingerprint)
        if raw != normalized or key != name(normalized):
            raise ValueError("Recovery journal record checksum mismatch.")
        marker = json.loads(raw)
        add(marker)

    def covered_rows(rows: dict[str, list[str]]) -> list[list[str]]:
        # The operator's fence establishes coverage. Use its time as an upper bound
        # on restored row timestamps if a source clock was ahead.
        return [
            [*rows[key][:-1], min(utc(rows[key][-1]), fenced_at).isoformat()]
            for key in sorted(rows)
        ]

    return baseline | {
        "captured_at": fenced_at.isoformat(),
        "journal_baseline_at": baseline_at.isoformat(),
        "deletions": covered_rows(deletions),
        "suppressions": covered_rows(suppressions),
    }
