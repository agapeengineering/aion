-- Synthetic fixture for an isolated staging recovery drill.
\set ON_ERROR_STOP on
BEGIN;
INSERT INTO users (id, email, verified_at) VALUES
    ('78130000-0000-4000-8000-000000000001', 'deleted-recovery@example.test', now()),
    ('78130000-0000-4000-8000-000000000002', 'retained-recovery@example.test', now()),
    ('78130000-0000-4000-8000-000000000003', 'isolated-recovery@example.test', now());
INSERT INTO profiles
    (user_id, revision, birth_date, lifespan_years, language, unit, hide_remaining)
VALUES
    ('78130000-0000-4000-8000-000000000001', 1, DATE '2000-01-01', 93, 'en', 'weeks', false),
    ('78130000-0000-4000-8000-000000000002', 1, DATE '2000-01-02', 89, 'es', 'years', true),
    ('78130000-0000-4000-8000-000000000003', 1, DATE '2000-01-03', 87, 'en', 'days', false);
INSERT INTO sessions
    (id, user_id, token_digest, csrf_digest, last_seen_at, expires_at, absolute_expires_at)
VALUES
    ('78130000-0000-4000-8001-000000000001', '78130000-0000-4000-8000-000000000001',
        sha256(convert_to('synthetic-recovery-deleted-session', 'UTF8')), sha256('old-csrf'),
        now(), now() + INTERVAL '1 hour', now() + INTERVAL '1 day'),
    ('78130000-0000-4000-8001-000000000002', '78130000-0000-4000-8000-000000000002',
        sha256(convert_to('synthetic-recovery-retained-session', 'UTF8')), sha256('old-csrf'),
        now(), now() + INTERVAL '1 hour', now() + INTERVAL '1 day');
INSERT INTO email_challenges
    (id, email, purpose, code_digest, browser_digest, expires_at)
VALUES
    ('78130000-0000-4000-8002-000000000001', 'deleted-recovery@example.test', 'login',
        sha256('drill'), sha256('drill'), now() + INTERVAL '10 minutes'),
    ('78130000-0000-4000-8002-000000000003', 'isolated-recovery@example.test', 'login',
        sha256('drill'), sha256('drill'), now() + INTERVAL '10 minutes');
INSERT INTO verification_mail (id, challenge_id, encrypted_payload, next_attempt_at, expires_at)
VALUES
    ('78130000-0000-4000-8003-000000000001', '78130000-0000-4000-8002-000000000001',
        '\x00', now(), now() + INTERVAL '10 minutes'),
    ('78130000-0000-4000-8003-000000000003', '78130000-0000-4000-8002-000000000003',
        '\x00', now(), now() + INTERVAL '10 minutes');
INSERT INTO reminder_mail
    (id, user_id, local_date, due_at, expires_at, next_attempt_at, lease_until,
     preference_revision, profile_revision, status, attempts, acceptance_unknown, encrypted_payload)
VALUES
    ('78130000-0000-4000-8004-000000000001', '78130000-0000-4000-8000-000000000002',
        CURRENT_DATE, now(), now() + INTERVAL '1 day', now(), now() + INTERVAL '10 minutes',
        1, 1, 'pending', 1, true, '\x00');
INSERT INTO reminder_preferences
    (user_id, revision, enabled, frequency, timezone, send_time, weekday, language, include_phrase,
     consent_at, notice_version, next_due_at, unsubscribe_digest, encrypted_token)
VALUES
    ('78130000-0000-4000-8000-000000000002', 1, true, 'weekly', 'UTC', '09:00', 0, 'es', false,
        now(), 'drill', now(), sha256('synthetic-recovery-unsubscribe'), '\x00');
COMMIT;
