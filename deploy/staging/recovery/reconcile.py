"""Build a transaction that reconciles an isolated restored Aion database."""

import argparse
import csv
import io
import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

SCHEMA = "0006_account_lifecycle"


def utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("Recovery times must be UTC.")
    return parsed


def marker_rows(document: dict) -> tuple[list, list]:
    if document["format"] != 1 or document["schema_revision"] != SCHEMA:
        raise ValueError("Unsupported recovery marker format or schema.")
    captured_at = utc(document["captured_at"])
    deletions = []
    for raw_user, digest, raw_timestamp in document["deletions"]:
        user = str(uuid.UUID(raw_user))
        timestamp = utc(raw_timestamp)
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or timestamp > captured_at:
            raise ValueError("Invalid account deletion marker.")
        deletions.append((user, "\\x" + digest, timestamp.isoformat()))

    suppressions = []
    for digest, reason, raw_timestamp in document["suppressions"]:
        timestamp = utc(raw_timestamp)
        if (
            not re.fullmatch(r"[0-9a-f]{64}", digest)
            or reason not in {"bounced", "complained", "suppressed"}
            or timestamp > captured_at
        ):
            raise ValueError("Invalid email suppression marker.")
        suppressions.append(("\\x" + digest, reason, timestamp.isoformat()))
    return deletions, suppressions


def copy_into(table: str, rows: list) -> str:
    data = io.StringIO()
    csv.writer(data, lineterminator="\n").writerows(rows)
    return f"COPY {table} FROM STDIN WITH (FORMAT csv);\n{data.getvalue()}\\.\n"


def reconciliation(manifest: dict, markers: dict, through: datetime) -> str:
    deletions, suppressions = marker_rows(markers)
    if manifest["format"] != 1 or manifest["schema_revision"] != SCHEMA:
        raise ValueError("Unsupported database backup format or schema.")
    snapshot_at = utc(manifest["snapshot_at"])
    captured_at = utc(markers["captured_at"])
    if captured_at < max(snapshot_at, through):
        raise ValueError("Independent recovery markers do not cover the requested time.")
    if markers["key_fingerprint"] != manifest["key_fingerprint"]:
        raise ValueError("The backup and marker copy use different application keys.")
    epoch = manifest.get("journal_epoch")
    if epoch is not None:
        if (
            not re.fullmatch(r"[0-9a-f]{32}", epoch)
            or markers.get("journal_epoch") != epoch
            or utc(markers["journal_baseline_at"]) > snapshot_at
        ):
            raise ValueError("The collected journal does not cover this snapshot's epoch.")
    elif "journal_epoch" in markers:
        raise ValueError("The snapshot did not record the selected recovery journal epoch.")
    return reconcile_sql(deletions, suppressions)


def reconcile_sql(deletions: list, suppressions: list) -> str:
    return (
        "BEGIN;\n"
        "CREATE TEMP TABLE recovered_deletions (LIKE deletion_ledger INCLUDING ALL);\n"
        "CREATE TEMP TABLE recovered_suppressions (LIKE email_suppressions INCLUDING ALL);\n"
        + copy_into("recovered_deletions", deletions)
        + copy_into("recovered_suppressions", suppressions)
        + """
DO $$
BEGIN
    IF (SELECT array_agg(version_num) FROM alembic_version)
        IS DISTINCT FROM ARRAY['0006_account_lifecycle']::varchar[] THEN
        RAISE EXCEPTION 'Unexpected schema revision';
    END IF;
    IF EXISTS (
        SELECT 1 FROM deletion_ledger JOIN recovered_deletions USING (user_id)
        WHERE deletion_ledger.email_digest <> recovered_deletions.email_digest
    ) THEN
        RAISE EXCEPTION 'Conflicting deletion marker';
    END IF;
    IF EXISTS (
        SELECT 1 FROM deletion_ledger LEFT JOIN recovered_deletions USING (user_id)
        WHERE recovered_deletions.user_id IS NULL
    ) OR EXISTS (
        SELECT 1 FROM email_suppressions LEFT JOIN recovered_suppressions USING (email_digest)
        WHERE recovered_suppressions.email_digest IS NULL
    ) THEN
        RAISE EXCEPTION 'Independent copy is missing markers already in the backup';
    END IF;
END $$;

INSERT INTO deletion_ledger SELECT * FROM recovered_deletions
ON CONFLICT (user_id) DO NOTHING;
INSERT INTO email_suppressions SELECT * FROM recovered_suppressions
ON CONFLICT (email_digest) DO NOTHING;

-- UUID identifies the deleted account even if the same address later signed up again.
DELETE FROM users USING deletion_ledger WHERE users.id = deletion_ledger.user_id;
-- Login challenges have no owner FK. Clear all restored challenges and their queued mail.
DELETE FROM email_challenges;
DELETE FROM sessions;
UPDATE reminder_mail
SET status = CASE WHEN acceptance_unknown THEN 'uncertain' ELSE 'cancelled' END,
    encrypted_payload = NULL, lease_until = NULL
WHERE status = 'pending';
UPDATE reminder_preferences
SET enabled = false, next_due_at = NULL, revision = revision + 1
WHERE enabled;
-- An older snapshot can undercount today's mail attempts. Resume with a fresh UTC window.
INSERT INTO rate_limit_buckets (namespace, subject_digest, window_start, attempts, expires_at)
SELECT 'verification_mail_daily', sha256(convert_to('verification_mail_daily', 'UTF8')),
       date_trunc('day', now(), 'UTC'), 2147483647,
       date_trunc('day', now(), 'UTC') + interval '24 hours'
ON CONFLICT (namespace, subject_digest, window_start) DO UPDATE SET attempts = EXCLUDED.attempts;
COMMIT;
"""
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("markers", type=Path)
    parser.add_argument("--through", required=True, help="Last known change time in UTC")
    args = parser.parse_args()
    try:
        program = reconciliation(
            json.loads(args.manifest.read_text()),
            json.loads(args.markers.read_text()),
            utc(args.through),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise SystemExit("Recovery input failed validation.") from exc
    print(program, end="")


if __name__ == "__main__":
    main()
