"""Capture a PostgreSQL snapshot or an independent copy of recovery markers."""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from reconcile import SCHEMA, marker_rows

CONFIG_FILES = (
    "compose.yaml",
    "manifest.json",
    "images.env",
    "nginx.conf",
    "deploy.sh",
    "init-postgres.sh",
    "migrate.py",
    "runtime-grants.sql",
    "prepare-state.py",
)
STATE_FILES = (
    "auth-keys.json",
    "postgres-password",
    "migrator-password",
    "migrator-url",
    "runtime-password",
    "runtime-url",
    "tls.crt",
    "tls.key",
)
EPOCH_FILE = "journal-epoch"
READ_MARKERS = """
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL timezone TO 'UTC';
SELECT json_build_object(
    'format', 1,
    'schema_revision', (SELECT version_num FROM alembic_version),
    'captured_at', transaction_timestamp(),
    'deletions', COALESCE((SELECT json_agg(
        json_build_array(user_id, encode(email_digest, 'hex'), deleted_at) ORDER BY user_id
    ) FROM deletion_ledger), '[]'::json),
    'suppressions', COALESCE((SELECT json_agg(
        json_build_array(encode(email_digest, 'hex'), reason, created_at) ORDER BY email_digest
    ) FROM email_suppressions), '[]'::json)
);
COMMIT;
"""


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def journal_epoch(state: Path) -> str | None:
    path = state / EPOCH_FILE
    if not path.exists() and not path.is_symlink():
        return None
    if not path.is_file() or path.is_symlink():
        raise ValueError("Invalid recovery journal epoch file.")
    epoch = path.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{32}", epoch):
        raise ValueError("Invalid recovery journal epoch.")
    return epoch


def check_writer_epoch(project: str, state: Path, epoch: str | None) -> None:
    running = subprocess.check_output(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            "label=com.docker.compose.service=api",
            "--format",
            "{{.ID}}",
        ],
        text=True,
    ).split()
    if not running:
        return
    for container in json.loads(subprocess.check_output(["docker", "inspect", *running])):
        env = dict(entry.split("=", 1) for entry in container["Config"]["Env"] if "=" in entry)
        epoch_path = env.get("AION_RECOVERY_JOURNAL_EPOCH_FILE")
        public_mail = env.get("AION_RESEND_PUBLIC_ACCOUNTS", "false").lower() in {
            "1",
            "on",
            "t",
            "true",
            "y",
            "yes",
        }
        if epoch is None and not public_mail and not epoch_path:
            continue
        if (
            epoch is None
            or not env.get("AION_RECOVERY_JOURNAL_SOCKET")
            or not any(
                mount["Destination"] == epoch_path
                and mount["Source"] == str(state / EPOCH_FILE)
                and mount["Type"] == "bind"
                and not mount["RW"]
                for mount in container["Mounts"]
            )
        ):
            raise ValueError("API journal configuration and snapshot state do not match.")


def capture(
    kind: str,
    release: Path,
    state: Path,
    target: Path,
    project: str,
) -> None:
    if project != "aion-staging" and not re.fullmatch(r"aion-recovery-[a-z0-9]+", project):
        raise ValueError("Select the staging project or a disposable recovery project.")
    if target.exists() or not state.is_dir() or state.is_symlink():
        raise ValueError("Choose a new capture directory and the private staging state directory.")
    files = [state / filename for filename in STATE_FILES]
    if stat.S_IMODE(state.stat().st_mode) != 0o700 or any(
        not path.is_file() or path.is_symlink() for path in files
    ):
        raise ValueError("Inconsistent staging state directory.")
    fingerprint = digest(state / "auth-keys.json")
    compose = [
        "docker",
        "compose",
        "-p",
        project,
        "--env-file",
        "images.env",
        "exec",
        "-T",
        "postgres",
    ]
    psql = [
        *compose,
        "psql",
        "-XqAt",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "postgres",
        "-d",
        "aion",
    ]
    options = {
        "cwd": release,
        "env": os.environ | {"AION_STAGING_STATE_DIR": str(state)},
    }
    target.mkdir(mode=0o700)
    if kind == "markers":
        data = subprocess.check_output([*psql, "-c", READ_MARKERS], **options, text=True)
        markers = json.loads(data)
        markers["key_fingerprint"] = fingerprint
        marker_rows(markers)
        if digest(state / "auth-keys.json") != fingerprint:
            raise ValueError("Application keys changed while capturing recovery markers.")
        (target / "markers.json").write_text(json.dumps(markers) + "\n")
        return

    revision = subprocess.check_output(
        [*psql, "-c", "SELECT version_num FROM alembic_version"], **options, text=True
    ).strip()
    if revision != SCHEMA:
        raise ValueError("Unexpected database schema revision.")
    epoch = journal_epoch(state)
    check_writer_epoch(project, state, epoch)
    release_manifest = json.loads((release / "manifest.json").read_text())
    snapshot_at = datetime.now(UTC)
    database = target / "database.dump"
    with database.open("wb") as stream:
        subprocess.run(
            [
                *compose,
                "pg_dump",
                "-U",
                "postgres",
                "-d",
                "aion",
                "-Fc",
                "--schema=public",
                "--no-owner",
                "--no-privileges",
                "--lock-wait-timeout=5s",
            ],
            **options,
            stdout=stream,
            check=True,
        )
    if (
        database.stat().st_size == 0
        or digest(state / "auth-keys.json") != fingerprint
        or journal_epoch(state) != epoch
    ):
        raise ValueError("Database capture is empty or the recovery configuration changed.")

    manifest = target / "snapshot.json"
    config = [release / filename for filename in CONFIG_FILES]
    if any(not path.is_file() or path.is_symlink() for path in config):
        raise ValueError("Incomplete or invalid release files.")
    keys = target / "keys.tar.gz"
    with tarfile.open(keys, "w:gz") as bundle:
        for path in files:
            bundle.add(path, arcname=path.name)
    with tarfile.open(keys, "r:gz") as bundle:
        archived_keys = bundle.extractfile("auth-keys.json")
        if archived_keys is None or hashlib.sha256(archived_keys.read()).hexdigest() != fingerprint:
            raise ValueError("Application keys changed before the backup was packaged.")
    manifest.write_text(
        json.dumps(
            {
                "format": 1,
                "schema_revision": revision,
                "snapshot_at": snapshot_at.isoformat(),
                "source_revision": release_manifest["source_revision"],
                "key_fingerprint": fingerprint,
                "keys_sha256": digest(keys),
                "database_sha256": digest(database),
                **({"journal_epoch": epoch} if epoch is not None else {}),
            },
            indent=2,
        )
        + "\n"
    )
    with tarfile.open(target / "snapshot.tar.gz", "w:gz") as bundle:
        for path in (manifest, database):
            bundle.add(path, arcname=path.name)
        for path in config:
            bundle.add(path, arcname=f"release/{path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("snapshot", "markers"))
    parser.add_argument("release", type=Path)
    parser.add_argument("state", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--project", default="aion-staging")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        capture(args.kind, args.release, args.state.absolute(), args.target, args.project)
    except (
        OSError,
        subprocess.CalledProcessError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit("Could not capture the Aion recovery input.") from exc


if __name__ == "__main__":
    main()
