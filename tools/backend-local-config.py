"""Create development-only secrets without displaying or rotating existing credentials."""

import secrets
from pathlib import Path
from urllib.parse import quote

directory = Path(__file__).resolve().parents[1] / ".local/backend"
directory.mkdir(parents=True, exist_ok=True, mode=0o700)
directory.chmod(0o700)
expected = ["postgres-password", "app-password", "database-url-container", "database-url-host"]
if any((directory / name).exists() for name in expected):
    if not all((directory / name).is_file() for name in expected):
        raise SystemExit(
            "Incomplete local configuration; reconcile it manually, do not rotate a DB"
        )
    print("Existing local configuration preserved.")
else:
    password = secrets.token_urlsafe(32)
    values = {
        "postgres-password": secrets.token_urlsafe(32),
        "app-password": password,
        "database-url-container": f"postgresql+psycopg://aion_app:{quote(password)}@postgres:5432/aion",
        "database-url-host": f"postgresql+psycopg://aion_app:{quote(password)}@127.0.0.1:15432/aion",
    }
    for name, value in values.items():
        path = directory / name
        with path.open("x") as stream:
            stream.write(value + "\n")
        # Parent is private; mount files read-only for non-root containers with a different UID.
        path.chmod(0o444)
    print("Development-only configuration created in the ignored private directory.")
