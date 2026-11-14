-- The application can check the schema revision and operate on its current data.
-- New migration objects receive no runtime grants until reviewed here.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM aion_runtime;
GRANT SELECT ON alembic_version TO aion_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    users, sessions, email_challenges, rate_limit_buckets, verification_mail,
    profiles, profile_mutations, reminder_preferences, reminder_mail
    TO aion_runtime;
GRANT SELECT, INSERT, DELETE ON email_events TO aion_runtime;
GRANT SELECT, INSERT ON email_suppressions TO aion_runtime;
GRANT INSERT ON deletion_ledger TO aion_runtime;
