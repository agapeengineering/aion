"""Build and export the Aion ARM64 staging package from a clean checkout."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = "linux/arm64"


def output(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build_package(destination: Path) -> None:
    if destination.exists():
        raise SystemExit("Choose a new output archive.")
    if output("git", "status", "--porcelain"):
        raise SystemExit("Build the staging package from a clean, reviewed Git revision.")
    node_version = (ROOT / ".node-version").read_text().strip()
    pnpm_version = json.loads((ROOT / "package.json").read_text())["packageManager"]
    if output("node", "--version") != f"v{node_version}" or pnpm_version != (
        f"pnpm@{output('pnpm', '--version')}"
    ):
        raise SystemExit("Use the Node and pnpm versions pinned by the repository.")

    revision = output("git", "rev-parse", "HEAD")
    subprocess.run(["pnpm", "install", "--frozen-lockfile"], cwd=ROOT, check=True)
    subprocess.run(
        ["pnpm", "build"],
        cwd=ROOT,
        env=os.environ
        | {"VITE_AION_AUTH": "1", "VITE_AION_AUTH_LOCAL": "0", "VITE_AION_REMINDERS": "0"},
        check=True,
    )
    version = json.loads((ROOT / "apps/web/dist/version.json").read_text())
    if version.get("sourceRevision") != revision or version.get("dirty") is not False:
        raise SystemExit("The web artifact does not match the clean source revision.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".aion-staging-", dir=destination.parent) as temporary:
        work = Path(temporary)
        payload = work / "aion-staging"
        shutil.copytree(
            ROOT / "deploy/staging", payload, ignore=shutil.ignore_patterns("__pycache__")
        )
        images = {}
        for name, context, dockerfile in (
            ("backend", "apps/backend", "apps/backend/Dockerfile"),
            ("web", ".", "deploy/web/Dockerfile"),
        ):
            iid_file = work / f"{name}.iid"
            subprocess.run(
                [
                    "docker",
                    "buildx",
                    "build",
                    "--load",
                    "--provenance=false",
                    "--platform",
                    PLATFORM,
                    "--iidfile",
                    str(iid_file),
                    "--label",
                    f"org.opencontainers.image.revision={revision}",
                    "--file",
                    dockerfile,
                    context,
                ],
                cwd=ROOT,
                check=True,
            )
            image_id = output(
                "docker", "image", "inspect", "--format", "{{.Id}}", iid_file.read_text().strip()
            )
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
                raise SystemExit("Docker returned an unexpected image ID.")
            platform = output(
                "docker", "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", image_id
            )
            if platform != PLATFORM:
                raise SystemExit("Docker returned an image for the wrong platform.")
            images[name] = image_id

        if output("git", "rev-parse", "HEAD") != revision or output("git", "status", "--porcelain"):
            raise SystemExit("The source changed while the images were building.")
        image_archive = payload / "images.tar"
        subprocess.run(
            ["docker", "image", "save", "--output", str(image_archive), *images.values()],
            cwd=ROOT,
            check=True,
        )
        (payload / "images.env").write_text(
            "".join(f"AION_{name.upper()}_IMAGE={image_id}\n" for name, image_id in images.items())
        )
        (payload / "manifest.json").write_text(
            json.dumps(
                {
                    "source_revision": revision,
                    "platform": PLATFORM,
                    "images": images,
                    "images_sha256": digest(image_archive),
                },
                indent=2,
            )
            + "\n"
        )
        archive = work / "package.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(payload, arcname="aion-staging")
        # Hard-link the complete archive into place and refuse to replace an existing file.
        os.link(archive, destination)

    print(f"Package {destination.name}  sha256:{digest(destination)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    build_package(parser.parse_args().archive.absolute())
