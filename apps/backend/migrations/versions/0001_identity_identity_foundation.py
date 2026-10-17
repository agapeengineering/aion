"""identity foundation"""

import sqlalchemy as sa
from alembic import op

revision = "0001_identity"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rate_limit_buckets",
        sa.Column("namespace", sa.String(length=48), nullable=False),
        sa.Column("subject_digest", sa.LargeBinary(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempts >= 0", name=op.f("ck_rate_limit_buckets_attempts_nonnegative")
        ),
        sa.CheckConstraint(
            "octet_length(subject_digest) = 32",
            name=op.f("ck_rate_limit_buckets_subject_digest_length"),
        ),
        sa.PrimaryKeyConstraint(
            "namespace", "subject_digest", "window_start", name=op.f("pk_rate_limit_buckets")
        ),
    )
    op.create_index(
        "ix_rate_limit_buckets_expiry", "rate_limit_buckets", ["expires_at"], unique=False
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "email = lower(btrim(email)) AND length(email) > 3",
            name=op.f("ck_users_canonical_email"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "email_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("code_digest", sa.LargeBinary(), nullable=False),
        sa.Column("browser_digest", sa.LargeBinary(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(purpose = 'login' AND user_id IS NULL) "
            "OR (purpose = 'reverify' AND user_id IS NOT NULL)",
            name=op.f("ck_email_challenges_purpose_owner"),
        ),
        sa.CheckConstraint(
            "purpose IN ('login', 'reverify')", name=op.f("ck_email_challenges_purpose")
        ),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 5", name=op.f("ck_email_challenges_attempt_range")
        ),
        sa.CheckConstraint(
            "email = lower(btrim(email)) AND length(email) > 3",
            name=op.f("ck_email_challenges_canonical_email"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_email_challenges_expiry_after_creation")
        ),
        sa.CheckConstraint(
            "octet_length(browser_digest) = 32",
            name=op.f("ck_email_challenges_browser_digest_length"),
        ),
        sa.CheckConstraint(
            "octet_length(code_digest) = 32", name=op.f("ck_email_challenges_code_digest_length")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_email_challenges_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_challenges")),
    )
    op.create_index("ix_email_challenges_expiry", "email_challenges", ["expires_at"], unique=False)
    op.create_index(
        "uq_email_challenges_active",
        "email_challenges",
        ["email", "purpose"],
        unique=True,
        postgresql_where=sa.text("consumed_at IS NULL AND invalidated_at IS NULL"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", sa.LargeBinary(), nullable=False),
        sa.Column("csrf_digest", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reverified_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "absolute_expires_at >= expires_at", name=op.f("ck_sessions_absolute_expiry")
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_sessions_expiry_after_creation")
        ),
        sa.CheckConstraint(
            "octet_length(csrf_digest) = 32", name=op.f("ck_sessions_csrf_digest_length")
        ),
        sa.CheckConstraint(
            "octet_length(token_digest) = 32", name=op.f("ck_sessions_token_digest_length")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_digest", name=op.f("uq_sessions_token_digest")),
    )
    op.create_index("ix_sessions_expiry", "sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index("ix_sessions_expiry", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(
        "uq_email_challenges_active",
        table_name="email_challenges",
        postgresql_where=sa.text("consumed_at IS NULL AND invalidated_at IS NULL"),
    )
    op.drop_index("ix_email_challenges_expiry", table_name="email_challenges")
    op.drop_table("email_challenges")
    op.drop_table("users")
    op.drop_index("ix_rate_limit_buckets_expiry", table_name="rate_limit_buckets")
    op.drop_table("rate_limit_buckets")
