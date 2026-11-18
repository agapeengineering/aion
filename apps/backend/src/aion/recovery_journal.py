"""Send minimal write-ahead recovery markers to the host's off-instance writer."""

import json
import socket
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from aion.database import SCHEMA_REVISION


class JournalUnavailable(Exception):
    """The journal did not confirm independent persistence."""


class RecoveryJournal:
    def __init__(self, path: Path, epoch: str, fingerprint: str) -> None:
        self.path, self.epoch, self.fingerprint = path, epoch, fingerprint

    def deletion(self, account: UUID, digest: bytes, at: datetime) -> None:
        self.append(at, deletions=[[str(account), digest.hex(), at.astimezone(UTC).isoformat()]])

    def suppression(self, digests: list[bytes], reason: str, at: datetime) -> None:
        stamp = at.astimezone(UTC).isoformat()
        self.append(at, suppressions=[[digest.hex(), reason, stamp] for digest in digests])

    def append(
        self,
        at: datetime,
        *,
        deletions: list[list[str]] | None = None,
        suppressions: list[list[str]] | None = None,
    ) -> None:
        marker = {
            "format": 1,
            "schema_revision": SCHEMA_REVISION,
            "journal_epoch": self.epoch,
            "key_fingerprint": self.fingerprint,
            "captured_at": at.astimezone(UTC).isoformat(),
            "deletions": deletions or [],
            "suppressions": suppressions or [],
        }
        message = (json.dumps(marker, separators=(",", ":"), sort_keys=True) + "\n").encode()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(9)
                connection.connect(str(self.path))
                connection.sendall(message)
                connection.shutdown(socket.SHUT_WR)
                with connection.makefile("rb") as reply:
                    if reply.readline(8) != b"stored\n":
                        raise JournalUnavailable
        except OSError:
            raise JournalUnavailable from None
