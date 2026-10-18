"""Owned calendar profiles, reset tombstones and bounded idempotency metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0004_profiles"
down_revision = "0003_mail_result"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("lifespan_years", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(2), nullable=True),
        sa.Column("unit", sa.String(16), nullable=True),
        sa.Column("hide_remaining", sa.Boolean(), nullable=True),
        sa.CheckConstraint("revision > 0", name=op.f("ck_profiles_revision_positive")),
        sa.CheckConstraint(
            "(birth_date IS NULL AND lifespan_years IS NULL AND language IS "
            "NULL AND unit IS NULL AND hide_remaining IS NULL) OR "
            "(birth_date IS NOT NULL AND lifespan_years IS NOT NULL AND "
            "language IS NOT NULL AND unit IS NOT NULL AND lifespan_years > "
            "0 AND extract(year FROM birth_date) >= 1 AND extract(year FROM "
            "birth_date) + lifespan_years <= 9999 "
            "AND language IN ('en', 'es') AND unit IN ('years', 'months', "
            "'weeks', 'days', 'hours', 'minutes', 'seconds') AND "
            "hide_remaining IS NOT NULL)",
            name=op.f("ck_profiles_complete_profile"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_profiles_user_id_users")
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_profiles")),
    )
    op.create_table(
        "profile_mutations",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("payload_digest", sa.LargeBinary(), nullable=False),
        sa.Column("result_revision", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "octet_length(payload_digest) = 32", name=op.f("ck_profile_mutations_digest_length")
        ),
        sa.CheckConstraint(
            "result_revision > 0", name=op.f("ck_profile_mutations_revision_positive")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_profile_mutations_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("user_id", "operation_id", name=op.f("pk_profile_mutations")),
    )


def downgrade():
    op.drop_table("profile_mutations")
    op.drop_table("profiles")
