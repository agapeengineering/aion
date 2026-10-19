"""Write EN/ES verification previews using synthetic data; never sends email."""

import argparse
from pathlib import Path

from aion.mail_content import verification_content, verification_html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".local/email-preview"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for language in ("en", "es"):
        args.output.joinpath(f"{language}.html").write_text(
            verification_html("00123456", language, "support@agape.engineering"),
            encoding="utf-8",
        )
        args.output.joinpath(f"{language}.txt").write_text(
            verification_content("00123456", language, "support@agape.engineering")[1],
            encoding="utf-8",
        )
    print("Synthetic EN/ES previews ready; no email sent.")


if __name__ == "__main__":
    main()
