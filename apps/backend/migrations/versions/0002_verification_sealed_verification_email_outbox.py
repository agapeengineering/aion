"""sealed verification email outbox"""

import sqlalchemy as sa
from alembic import op

revision = "0002_verification"
down_revision = "0001_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "verification_mail",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("challenge_id", sa.Uuid(), nullable=False),
        sa.Column("encrypted_payload", sa.LargeBinary(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'cancelled', 'failed')",
            name=op.f("ck_verification_mail_status"),
        ),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 6", name=op.f("ck_verification_mail_attempt_range")
        ),
        sa.ForeignKeyConstraint(
            ["challenge_id"],
            ["email_challenges.id"],
            name=op.f("fk_verification_mail_challenge_id_email_challenges"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification_mail")),
        sa.UniqueConstraint("challenge_id", name=op.f("uq_verification_mail_challenge_id")),
    )
    op.create_index(
        "ix_verification_mail_due", "verification_mail", ["status", "next_attempt_at"], unique=False
    )


def downgrade():
    op.drop_index("ix_verification_mail_due", table_name="verification_mail")
    op.drop_table("verification_mail")
