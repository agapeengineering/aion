"""Create private staging credentials and a loopback TLS certificate."""

import argparse
import base64
import json
import os
import secrets
import stat
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


def prepare(state: Path) -> None:
    roles = ("postgres", "migrator", "runtime")
    expected = {
        *(f"{role}-password" for role in roles),
        "migrator-url",
        "runtime-url",
        "auth-keys.json",
        "tls.key",
        "tls.crt",
    }
    if state.exists() or state.is_symlink():
        if (
            state.is_symlink()
            or not state.is_dir()
            or stat.S_IMODE(state.stat().st_mode) != 0o700
            or any(not (state / name).is_file() or (state / name).is_symlink() for name in expected)
        ):
            raise SystemExit("Reconcile the existing staging state directory before deploying.")
        result = subprocess.run(
            ["openssl", "x509", "-in", str(state / "tls.crt"), "-noout", "-checkend", "0"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode:
            raise SystemExit("Renew the staging TLS certificate before deploying.")
        print("Existing staging credentials and TLS certificate preserved.")
        return

    state.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".aion-state-", dir=state.parent) as temporary:
        pending = Path(temporary)
        for role in roles:
            password = secrets.token_urlsafe(32)
            (pending / f"{role}-password").write_text(password + "\n")
            if role != "postgres":
                (pending / f"{role}-url").write_text(
                    f"postgresql+psycopg://aion_{role}:{password}@postgres:5432/aion\n"
                )
        (pending / "auth-keys.json").write_text(
            json.dumps(
                {
                    name: base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
                    for name in ("mac", "csrf", "seal")
                }
            )
        )
        result = subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "30",
                "-keyout",
                str(pending / "tls.key"),
                "-out",
                str(pending / "tls.crt"),
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode:
            raise SystemExit("Could not generate the staging TLS certificate.")
        # Docker Compose bind-mounts the files into containers with distinct non-root UIDs.
        # The containing directory stays owner-private.
        for name in expected:
            (pending / name).chmod(0o444)
        pending.rename(state)
    print("Staging credentials and TLS certificate created.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    arguments = parser.parse_args()
    os.umask(0o077)
    prepare(arguments.state.absolute())
