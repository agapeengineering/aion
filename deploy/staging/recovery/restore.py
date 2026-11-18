"""Restore Aion into a disposable PostgreSQL project and reconcile before starting the API."""

import argparse
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path

from capture import CONFIG_FILES, STATE_FILES, digest
from reconcile import SCHEMA, reconciliation, utc


def start_database(release: Path, state: Path, project: str) -> list[str]:
    base = ["docker", "compose", "-p", project, "--env-file", "images.env"]
    options = {
        "cwd": release,
        "env": os.environ | {"AION_STAGING_STATE_DIR": str(state)},
    }
    model = json.loads(
        subprocess.check_output([*base, "config", "--format", "json"], **options, text=True)
    )
    model["services"] = {"postgres": model["services"]["postgres"]}
    model["networks"] = {"database": model["networks"]["database"]}
    model["secrets"] = {
        key: model["secrets"][key]
        for key in ("postgres_password", "migrator_password", "runtime_password")
    }
    config_path = release / "restore-compose.json"
    config_path.write_text(json.dumps(model))
    command = ["docker", "compose", "-p", project, "-f", str(config_path)]
    subprocess.run([*command, "up", "-d", "--wait", "postgres"], check=True)
    return [*command, "exec", "-T", "postgres"]


def unpack(archive: Path, target: Path, expected: set[str]) -> None:
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        if len(members) != len(expected) or {entry.name for entry in members} != expected:
            raise ValueError("Unexpected recovery archive contents.")
        if any(not entry.isfile() for entry in members):
            raise ValueError("Recovery archives must only contain regular files.")
        bundle.extractall(target, filter="data")


def restore(
    inputs: Path, target: Path, project: str, through: str, *, require_journal: bool = False
) -> None:
    if not re.fullmatch(r"aion-recovery-[a-z0-9]+", project) or target.exists():
        raise ValueError("Choose a new disposable recovery project and directory.")
    target.mkdir(mode=0o700)
    unpack(
        inputs / "snapshot.tar.gz",
        target,
        {
            "snapshot.json",
            "database.dump",
            *(f"release/{name}" for name in CONFIG_FILES),
        },
    )
    manifest = json.loads((target / "snapshot.json").read_text())
    if require_journal and not manifest.get("journal_epoch"):
        raise ValueError("Public account recovery requires a snapshot with a journal epoch.")
    if (
        digest(target / "database.dump") != manifest["database_sha256"]
        or digest(inputs / "keys.tar.gz") != manifest["keys_sha256"]
    ):
        raise ValueError("Recovery archive checksum mismatch.")
    unpack(inputs / "keys.tar.gz", target / "state", set(STATE_FILES))
    if digest(target / "state/auth-keys.json") != manifest["key_fingerprint"]:
        raise ValueError("Restored application keys do not match the backup.")
    (target / "state").chmod(0o700)
    for name in STATE_FILES:
        (target / "state" / name).chmod(0o444)
    program = reconciliation(
        manifest, json.loads((inputs / "markers.json").read_text()), utc(through)
    )

    # Reuse the exact database and bootstrap from the restored Compose configuration.
    # The isolated project contains only the database until reconciliation has committed.
    volume = subprocess.run(
        ["docker", "volume", "inspect", f"{project}_database"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if volume.returncode == 0:
        raise ValueError("The disposable recovery volume already exists.")
    release = target / "release"
    docker = start_database(release, target / "state", project)
    with (target / "database.dump").open("rb") as stream:
        subprocess.run(
            [
                *docker,
                "pg_restore",
                "-U",
                "postgres",
                "-d",
                "aion",
                "--role=aion_migrator",
                "--no-owner",
                "--no-privileges",
                "--clean",
                "--if-exists",
                "--exit-on-error",
                "--single-transaction",
            ],
            stdin=stream,
            check=True,
        )
    subprocess.run(
        [
            *docker,
            "psql",
            "-Xq",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "aion",
        ],
        input=program
        + "\nBEGIN;\nREVOKE ALL ON SCHEMA public FROM PUBLIC;\n"
        + "GRANT USAGE ON SCHEMA public TO aion_runtime;\n"
        + (release / "runtime-grants.sql").read_text()
        + "\nCOMMIT;\n",
        text=True,
        check=True,
    )
    revision = subprocess.check_output(
        [
            *docker,
            "psql",
            "-XqAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "aion",
            "-c",
            "SELECT version_num FROM alembic_version",
        ],
        text=True,
    ).strip()
    if revision != SCHEMA:
        raise ValueError("Restored database schema does not match the reviewed backend.")
    print(f"Restored and reconciled schema {revision}. No API or worker started.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("project")
    parser.add_argument("--through", required=True)
    parser.add_argument(
        "--require-journal",
        action="store_true",
        help="Require journal coverage for public accounts",
    )
    args = parser.parse_args()
    os.umask(0o077)
    try:
        restore(
            args.inputs.absolute(),
            args.target.absolute(),
            args.project,
            args.through,
            require_journal=args.require_journal,
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(
            "Aion restore or reconciliation failed. Leave traffic and sends disabled."
        ) from exc


if __name__ == "__main__":
    main()
