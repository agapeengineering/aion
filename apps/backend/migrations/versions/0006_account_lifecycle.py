"""Bind reverification to a session; retain minimal deletion markers independently."""

import sqlalchemy as sa
from alembic import op

revision = "0006_account_lifecycle"
down_revision = "0005_reminders"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("email_challenges", sa.Column("session_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_email_challenges_session_id_sessions",
        "email_challenges",
        "sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_email_challenges_purpose_session",
        "email_challenges",
        "(purpose = 'login' AND session_id IS NULL) OR "
        "(purpose = 'reverify' AND session_id IS NOT NULL)",
    )
    op.create_table(
        "deletion_ledger",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("email_digest", sa.LargeBinary(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("deletion_ledger")
    op.drop_constraint("ck_email_challenges_purpose_session", "email_challenges", type_="check")
    op.drop_constraint(
        "fk_email_challenges_session_id_sessions", "email_challenges", type_="foreignkey"
    )
    op.drop_column("email_challenges", "session_id")
