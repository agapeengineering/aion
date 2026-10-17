"""Regenerate only the implemented API contract, without connecting to a database."""

import argparse
import json
from pathlib import Path

from aion.main import create_app

target = Path(__file__).resolve().parents[1] / "docs/api/openapi.json"
output = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--check", action="store_true")
if parser.parse_args().check:
    if not target.is_file() or target.read_text() != output:
        raise SystemExit("API export differs; regenerate docs/api/openapi.json")
else:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(output)
print("Implemented API contract is current.")
