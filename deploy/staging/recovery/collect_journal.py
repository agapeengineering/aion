"""Collect a complete, fenced S3 recovery epoch using an independent operator identity."""

import argparse
import base64
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from journal_inputs import MAX_EVENT_BYTES, merge, prefix
from reconcile import utc


def collect(bucket: str, region: str, owner: str, path: str) -> tuple[dict, dict[str, bytes]]:
    def s3(operation: str, *options: str) -> object:
        outcome = subprocess.run(
            [
                "aws",
                "--region",
                region,
                "--no-cli-pager",
                "--output",
                "json",
                "s3api",
                operation,
                "--bucket",
                bucket,
                "--expected-bucket-owner",
                owner,
                *options,
            ],
            check=True,
            capture_output=True,
        )
        return json.loads(outcome.stdout)

    with TemporaryDirectory(prefix="aion-journal-read.") as work:
        target = Path(work) / "record.json"

        def download(key: str) -> bytes:
            info = s3("get-object", "--key", key, "--checksum-mode", "ENABLED", str(target))
            raw = target.read_bytes()
            expected = base64.b64encode(hashlib.sha256(raw).digest()).decode()
            if not isinstance(info, dict) or info.get("ChecksumSHA256") != expected:
                raise ValueError("Independent recovery input failed its storage checksum.")
            return raw

        baseline = json.loads(download(path + "baseline.json"))
        events = path + "events/"
        # The AWS CLI automatically paginates this JSON query when called without a result limit.
        keys = s3("list-objects-v2", "--prefix", events, "--query", "Contents[].Key") or []
        if not isinstance(keys, list) or len(keys) != len(set(keys)):
            raise ValueError("Invalid recovery journal listing.")
        records = {}
        for key in keys:
            if not isinstance(key, str) or not key.startswith(events):
                raise ValueError("Unexpected key in the recovery journal listing.")
            record = download(key)
            if len(record) > MAX_EVENT_BYTES:
                raise ValueError("Oversized record in the recovery journal listing.")
            records[key.removeprefix(events)] = record
        return baseline, records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bucket")
    parser.add_argument("region")
    parser.add_argument("owner")
    parser.add_argument("epoch")
    parser.add_argument(
        "fingerprint", help="Application key fingerprint from the selected snapshot"
    )
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--fenced-at",
        required=True,
        help="Verified cutoff of all source writers in UTC",
    )
    parser.add_argument("--drill", action="store_true")
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        fenced_at = utc(args.fenced_at)
        if fenced_at > datetime.now(UTC):
            raise ValueError("The source fence must have already happened.")
        path = prefix(args.epoch, drill=args.drill, production=args.production)
        baseline, records = collect(args.bucket, args.region, args.owner, path)
        result = merge(baseline, records, args.epoch, args.fingerprint, fenced_at)
        with args.destination.open("x") as target:
            json.dump(result, target)
        print(f"Collected and verified {len(records)} independent recovery journal objects.")
    except (
        OSError,
        TypeError,
        ValueError,
        KeyError,
        subprocess.CalledProcessError,
    ) as exc:
        raise SystemExit(
            "Could not prove recovery journal coverage. Keep traffic and sends disabled."
        ) from exc


if __name__ == "__main__":
    main()
