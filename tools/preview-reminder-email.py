"""Render synthetic EN/ES calendar reminders locally; never sends email."""

from datetime import UTC, date, datetime
from pathlib import Path

from aion.models import Profile, ReminderPreference
from aion.phrases import weekly_collection
from aion.reminder_content import render_reminder


def main() -> None:
    output = Path(".local/email-preview")
    output.mkdir(parents=True, exist_ok=True)
    for language in ("en", "es"):
        profile = Profile(birth_date=date(2000, 1, 1), lifespan_years=90, hide_remaining=False)
        pref = ReminderPreference(timezone="UTC", language=language, include_phrase=False)
        payload, _ = render_reminder(
            profile,
            pref,
            datetime(2026, 10, 18, 9, tzinfo=UTC),
            weekly_collection(),
            origin="https://aion.example.test",
            email="preview@example.test",
            sender="Aion <aion@example.test>",
            reply_to="support@example.test",
            token="synthetic-preview-unsubscribe-token",
        )
        for extension, key in (("html", "html"), ("txt", "text")):
            output.joinpath(f"reminder-{language}.{extension}").write_text(
                str(payload[key]), encoding="utf-8"
            )
    print("Synthetic reminder previews ready; no email sent.")


if __name__ == "__main__":
    main()
