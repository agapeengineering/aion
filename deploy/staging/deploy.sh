#!/bin/sh
set -eu

cd "$(dirname "$0")"
if [ "${1:-}" = "--check" ]; then
    check_only=true
    shift
else
    check_only=false
fi
if [ "$#" -ne 0 ]; then
    printf '%s\n' "Usage: sh deploy.sh [--check]" >&2
    exit 2
fi
: "${AION_STAGING_STATE_DIR:?Set an absolute path for persistent staging state}"
case "$AION_STAGING_STATE_DIR" in
    /*) ;;
    *) printf '%s\n' "The staging state path must be absolute." >&2; exit 1 ;;
esac

if [ "$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')" != linux/arm64 ]; then
    printf '%s\n' "Use a Linux ARM64 Docker engine for this release." >&2
    exit 1
fi

python3 - <<'PY'
import hashlib
import json
import re
from pathlib import Path

manifest = json.loads(Path("manifest.json").read_text())
revision = manifest["source_revision"]
images = manifest["images"]
if (
    manifest["platform"] != "linux/arm64"
    or not re.fullmatch(r"[0-9a-f]{40}", revision)
    or set(images) != {"backend", "web"}
    or not all(re.fullmatch(r"sha256:[0-9a-f]{64}", image) for image in images.values())
):
    raise SystemExit("Invalid release manifest.")
expected_env = "".join(
    f"AION_{name.upper()}_IMAGE={images[name]}\n" for name in ("backend", "web")
)
if Path("images.env").read_text() != expected_env:
    raise SystemExit("The image references differ from the release manifest.")
with Path("images.tar").open("rb") as stream:
    if hashlib.file_digest(stream, "sha256").hexdigest() != manifest["images_sha256"]:
        raise SystemExit("Image archive checksum mismatch.")
print(f"Verified image archive for source {revision}.")
PY

if "$check_only"; then
    docker compose -p aion-staging --env-file images.env config --quiet
    exit 0
fi

# Protect the persistent DB credentials from accidental regeneration.
if docker volume inspect aion-staging_database >/dev/null 2>&1 &&
   [ ! -d "$AION_STAGING_STATE_DIR" ]; then
    printf '%s\n' "The staging database volume exists. Recover its existing state directory." >&2
    exit 1
fi
python3 ./prepare-state.py "$AION_STAGING_STATE_DIR"

set -a
. ./images.env
set +a
docker image load --input images.tar >/dev/null
for image in "$AION_BACKEND_IMAGE" "$AION_WEB_IMAGE"; do
    actual_image="$(docker image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}}' "$image")"
    if [ "$actual_image" != "$image linux/arm64" ]; then
        printf '%s\n' "Loaded image does not match the package manifest." >&2
        exit 1
    fi
done

docker compose -p aion-staging --env-file images.env config --quiet
docker compose -p aion-staging --env-file images.env up -d --no-build --wait --wait-timeout 120
