"""Prepare ignored local Resend files without reading/displaying a key or enabling delivery."""

import argparse
import getpass
from pathlib import Path

root = Path(__file__).resolve().parents[1]
directory = root / ".local/resend"
directory.mkdir(parents=True, exist_ok=True, mode=0o700)
directory.chmod(0o700)
settings = directory / "settings.env"
if not settings.exists():
    settings.write_text(
        "# Configure a working Reply-To and explicit recipients before enabling.\n"
        "AION_EMAIL_FROM=Aion <aion@mail.agape.engineering>\n"
        "AION_EMAIL_REPLY_TO=\n"
        "AION_RESEND_ALLOWED_RECIPIENTS=[]\n"
    )
    settings.chmod(0o600)
key = directory / "api-key"
if not key.exists():
    key.touch(mode=0o600)
print("Local Resend files prepared/preserved. Populate them before enabling; no email sent.")

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--set-key", action="store_true", help="Read a key securely from the local terminal"
)
if parser.parse_args().set_key:
    value = getpass.getpass("Resend sending-only API key (hidden): ").strip()
    if not value.startswith("re_") or len(value) < 10 or any(x.isspace() for x in value):
        raise SystemExit("Invalid key format; existing file preserved")
    key.chmod(0o600)
    key.write_text(value + "\n")
    key.chmod(0o444)
    print("Key stored in the private local directory with container-readable file permissions.")
