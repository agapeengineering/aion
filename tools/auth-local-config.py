"""Generate local-only auth/TLS secrets; never display or rotate an existing key bundle."""

import base64
import json
import secrets
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
directory = root / ".local/auth"
directory.mkdir(parents=True, exist_ok=True, mode=0o700)
directory.chmod(0o700)
bundle = directory / "keys.json"
if not bundle.exists():
    with bundle.open("x") as stream:
        json.dump(
            {
                name: base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
                for name in ["mac", "csrf", "seal"]
            },
            stream,
        )
    bundle.chmod(0o444)
key, cert = directory / "tls.key", directory / "tls.crt"
if key.exists() != cert.exists():
    raise SystemExit("Incomplete local TLS configuration; reconcile explicitly")
if not key.exists():
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
            str(key),
            "-out",
            str(cert),
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ],
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit("Local test certificate generation failed")
    key.chmod(0o444)
    cert.chmod(0o444)
config = (root / "deploy/web/default.conf").read_text()
assert config.count("listen 8080;") == 1
(directory / "nginx.conf").write_text(
    config.replace(
        "listen 8080;",
        "listen 8080;\n    listen 8443 ssl;\n"
        "    ssl_certificate /run/secrets/dev_cert;\n"
        "    ssl_certificate_key /run/secrets/dev_key;\n"
        "    ssl_protocols TLSv1.2 TLSv1.3;",
    )
    + "\n# Keep one browser origin for host-only auth cookies and Origin validation.\n"
    + "server {\n"
    + "    listen 8443 ssl;\n"
    + "    server_name localhost;\n"
    + "    ssl_certificate /run/secrets/dev_cert;\n"
    + "    ssl_certificate_key /run/secrets/dev_key;\n"
    + "    ssl_protocols TLSv1.2 TLSv1.3;\n"
    + "    access_log off;\n"
    + "    return 308 https://127.0.0.1:18443$request_uri;\n"
    + "}\n"
)
print("Local auth keys preserved/created; local test TLS and proxy configuration ready.")
