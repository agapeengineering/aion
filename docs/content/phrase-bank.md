# Phrase content and weekly publication

Aion keeps editorial content in versioned JSON, reviewed with the code. PostgreSQL stores consent, schedules and delivery metadata; it does not duplicate the phrase catalogue. No admin service or CSV parser is needed.

- `apps/backend/src/aion/content/original-phrases.json`: the eight original EN/ES calendar phrases, shared with the web app. These are separate from the attributed weekly collection.
- `apps/backend/src/aion/content/weekly-phrases.json`: approved attributed passages and their publication order. Currently empty, pending editorial validation. No research drafts have been imported.
- [JSON schema](weekly-phrases.schema.json): generated from the Python validator; backend CI checks for drift.

## Global order

`anchorSunday` is fixed at **2026-10-18**. `sequence[0]` serves October 18–24, `sequence[1]` October 25–31, and so on, using the reminder's intended local date. All subscribers receive the same passage for that calendar week, regardless of signup date. The schedule defaults to Sunday at 09:00 in the chosen IANA timezone. Daily reminders reuse that week's passage; changing weekday does not restart the sequence.

Published entries and past sequence positions are immutable. Append future slots in order, keep stable IDs, and increment `collectionVersion` on each reviewed content release. Corrections require explicit editorial review. Do not reorder the collection when importing additional proposals. There is no automatic wrapping, random selection or catch-up email. A missing slot prevents phrase enrollment for that scheduled week and skips an existing phrase-enabled delivery; calendar-only reminders continue. Publish sufficient future slots before enabling attributed reminders.

## Entry contract

Each phrase records `id`, `author`, `work`, exact `location`, `original_language`, exact `original`, HTTPS `source_url`, `rights`, and `approved`. Both `en` and `es` contain `text`, `translator`, translation `source`, separate `rights`, and `approved`. For an original already in a delivery language, record that fact explicitly as translator/source metadata rather than inventing a translation. Approval must cover the exact original and both translations, including publication rights; source verification alone does not grant rights.

`sequence` lists the stable IDs in the chosen publication order. Only fully approved entries with complete attribution and rights can be referenced. Keep rejected/research material outside the product catalogue. The emails show the chosen translation, author, work, location, translator and original source link; the complete provenance stays in JSON for review.

Run `uv run --project apps/backend --locked python tools/validate-phrases.py` before review. Backend checks include the validator. Rebuild/restart the worker after changing content: packaged content is cached per process. Pending quote jobs retain their selected ID and collection version; a content-version change cancels them rather than silently changing a retry body. Email payloads are encrypted temporarily and erased on acceptance, cancellation or expiry.

A CSV may be an editorial interchange format later; it is not the runtime source of truth. Importers must preserve the same schema, provenance and reviewed publication order.
