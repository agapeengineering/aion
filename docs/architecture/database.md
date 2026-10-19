# Aion data model

Status: implementation map, not a claim of a deployed account service. The public R1 site still stores calendar settings only in each browser. The local backend foundation has four application tables under migration `0001_identity`; the signup/login slice adds `verification_mail` in `0002_verification`. Migration `0003_mail_result` adds provider acceptance ID/uncertainty metadata. Migration `0004_profiles` adds `profiles` and `profile_mutations`. Migration `0005_reminders` adds consent/schedules, reminder delivery jobs, minimal events and independent suppression. `alembic_version` tracks schema revision separately. The accepted [R2 specification](../requirements/backend-release-specification.md) defines the planned additions.

![Implemented and planned Aion data](database.svg)

The overview is generated from [Graphviz source](database.dot): `dot -Tsvg docs/architecture/database.dot -o docs/architecture/database.svg`. Solid boxes are implemented locally; dashed boxes remain planned. This authored overview includes plans; it is separate from the automatically generated implemented-schema diagram linked below.

## Implemented schema — generated automatically

See the [ERAlchemy-generated schema diagram](database-schema.md) and [canonical Graphviz source](database-schema.dot). They are reflected from a fresh schema built by Alembic migrations; backend checks fail if the committed text is stale. [Generate, render and inspect it locally](../development/database-documentation.md). Exact indexes, uniqueness and policy behavior remain in migrations/tests; `verification_mail.challenge_id` is unique, allowing at most one delivery record per challenge.

A first-login challenge has **no user foreign key**: an account is created only after successful verification. Reverification challenges belong to an existing user. Sessions/challenges referencing a deleted user cascade; this is a schema property, not an implemented account-deletion workflow. Rate counters deliberately do not require a user, so signup and nonexistent addresses receive the same abuse protection. The active challenge index permits only one unconsumed/non-invalidated challenge per email/purpose; resending invalidates its predecessor transactionally.

## Implemented account profiles

`profiles.user_id` is both the primary key and an owning user foreign key: each account has zero or one current profile row. A complete profile stores date-only birth date, lifespan, language, primary unit and remaining-figure visibility. There are no ticking counters or rows per week. Reset clears all five fields while increasing the revision; this tombstone prevents an old offline device from recreating a deleted profile with revision zero.

`profile_mutations` stores owner + operation UUID, keyed request digest, resulting revision and creation time for 30 days. It retains no prior profile bodies. The worker removes expired operation metadata. Revision checking continues to reject stale operations after metadata expires. Both tables cascade when their owning user is deleted; the account-deletion workflow is still pending. The generated renderer infers cardinalities from columns, so its users/profiles edge does not express the optional absence of the child row; this description and the migration are authoritative.

See the [implemented sync API and browser behavior](../api/profile-contract.md).

## Implemented reminder data

Migration `0005_reminders` adds `reminder_preferences` (optional owner row, explicit consent and revisioned local schedule), `reminder_mail` (owner/date uniqueness, expiring leases, sealed temporary snapshots and selected phrase metadata), `email_events` (minimal deduplicated provider events), and `email_suppressions` (keyed identifiers independent of active users). The verification outbox remains separate. See the [dispatch contract](../api/reminder-contract.md) and generated schema for actual fields and constraints.

Profile reset stops enrollment. Preference/profile changes cancel obsolete queued payloads. Suppression persists independently of a deleted user, but the complete account-deletion workflow and independently retained deletion ledger are **not implemented**. Backup reconciliation remains a release gate.

## Phrase bank and other data outside PostgreSQL

The original EN/ES calendar bank and approved attributed weekly bank are versioned JSON in `apps/backend/src/aion/content/`. The original bank is shared with the web app; the weekly bank is consumed by the reminder worker and starts empty pending editorial approval. It has no per-user rows or CRUD service. Global publication order starts October 18, 2026; metadata records the selected ID/content version. See the [phrase content strategy](../content/phrase-bank.md).

Guest settings and downloaded PNGs remain device-owned. Session credentials stay in HttpOnly cookies; only digests belong in PostgreSQL. Application encryption/HMAC keys belong in secret configuration, never in the same tables, source files, diagrams or logs. The server reads account settings to send reminders; this is not end-to-end encryption. See the [authentication contract](../api/authentication-contract.md) and [backend setup](../development/backend-setup.md) for implementation boundaries.
