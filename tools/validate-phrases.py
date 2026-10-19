"""Validate the packaged JSON content without importing private research artifacts."""

import json
from pathlib import Path

from aion.phrases import Collection, original_phrases, weekly_collection


def main() -> None:
    originals = original_phrases()
    assert len({p["id"] for p in originals}) == len(originals)
    assert all(p["en"].strip() and p["es"].strip() for p in originals)
    bank = weekly_collection()
    target = Path(__file__).resolve().parents[1] / "docs/content/weekly-phrases.schema.json"
    schema = json.dumps(Collection.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
    if target.read_text() != schema:
        raise SystemExit("Phrase schema documentation is stale; regenerate it from Collection")
    print(
        f"Phrase content valid: {len(originals)} originals; "
        f"{len(bank.sequence)} published weekly slots."
    )


if __name__ == "__main__":
    main()
