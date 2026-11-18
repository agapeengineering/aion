"""A local Unix socket that acknowledges only successfully stored S3 marker objects."""

import argparse
import fcntl
import hashlib
import os
import socketserver
import subprocess
import uuid
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory

from capture import journal_epoch
from journal_inputs import MAX_EVENT_BYTES, canonical_event, name, prefix

AWS_IMAGE = (
    "docker.io/amazon/aws-cli:2.32.0@"
    "sha256:4090597cd26166b53219e6e6d40c0267681a7c9a8b69e1d92722ff5a0cd6705a"
)


class JournalWriter:
    def __init__(self, bucket: str, region: str, account: str, path: str) -> None:
        self.bucket, self.region, self.account, self.path = (
            bucket,
            region,
            account,
            path,
        )

    def store(self, record: bytes) -> None:
        container = "aion-journal-" + uuid.uuid4().hex
        with TemporaryDirectory(prefix="aion-journal-put.") as directory:
            (Path(directory) / "record.json").write_bytes(record)
            try:
                result = subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--pull=never",
                        "--name",
                        container,
                        "--network",
                        "host",
                        "--volume",
                        f"{directory}:/aws:ro",
                        "--env",
                        "AWS_MAX_ATTEMPTS=1",
                        "--env",
                        "AWS_PAGER=",
                        AWS_IMAGE,
                        "--region",
                        self.region,
                        "--cli-connect-timeout",
                        "2",
                        "--cli-read-timeout",
                        "3",
                        "s3api",
                        "put-object",
                        "--bucket",
                        self.bucket,
                        "--key",
                        self.path + "events/" + name(record),
                        "--body",
                        "record.json",
                        "--expected-bucket-owner",
                        self.account,
                        "--if-none-match",
                        "*",
                        "--server-side-encryption",
                        "AES256",
                        "--checksum-algorithm",
                        "SHA256",
                    ],
                    capture_output=True,
                    timeout=6,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                subprocess.run(
                    ["docker", "rm", "-f", container],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
                raise ValueError("Off-instance journal write did not complete.") from exc
            # A byte-identical retry can find the content-addressed object already present.
            if result.returncode and b"(PreconditionFailed)" not in result.stderr:
                raise ValueError("Off-instance journal write failed.")


def serve(
    socket: Path,
    epoch: str,
    fingerprint: str,
    write: Callable[[bytes], None],
    group: int,
) -> None:
    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            self.connection.settimeout(1)
            try:
                payload = self.rfile.read(MAX_EVENT_BYTES + 1)
                write(canonical_event(payload, epoch, fingerprint))
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                subprocess.SubprocessError,
            ):
                # The journal contains keyed identifiers. Never log requests or AWS output.
                print("Aion recovery journal append was not acknowledged.", flush=True)
                return
            with suppress(OSError):
                self.wfile.write(b"stored\n")

    with socket.with_suffix(".lock").open("ab") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if socket.is_symlink() or (socket.exists() and not socket.is_socket()):
            raise ValueError("The journal path is not a Unix socket.")
        socket.unlink(missing_ok=True)
        with socketserver.UnixStreamServer(str(socket), Handler) as server:
            try:
                os.chown(socket, -1, group)
                socket.chmod(0o660)
                server.serve_forever()
            finally:
                socket.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("socket", type=Path)
    parser.add_argument("--group", type=int, default=10001)
    parser.add_argument("--drill", action="store_true")
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        state = Path(os.environ["AION_STAGING_STATE_DIR"])
        epoch = journal_epoch(state)
        if epoch is None:
            raise ValueError("The state directory has no active journal epoch.")
        keys = state / "auth-keys.json"
        fingerprint = hashlib.sha256(keys.read_bytes()).hexdigest()
        writer = JournalWriter(
            os.environ["AION_RECOVERY_BUCKET"],
            os.environ["AION_RECOVERY_REGION"],
            os.environ["AION_RECOVERY_ACCOUNT"],
            prefix(epoch, drill=args.drill, production=args.production),
        )
        serve(args.socket, epoch, fingerprint, writer.store, args.group)
    except (OSError, KeyError, ValueError) as exc:
        raise SystemExit("Could not start the private Aion recovery journal.") from exc


if __name__ == "__main__":
    main()
