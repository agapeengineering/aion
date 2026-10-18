"""Track provider acceptance separately from inbox delivery and uncertain sends."""

import sqlalchemy as sa
from alembic import op

revision = "0003_mail_result"
down_revision = "0002_verification"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("verification_mail", sa.Column("provider_message_id", sa.String(64)))
    op.add_column(
        "verification_mail",
        sa.Column("acceptance_unknown", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.drop_constraint(op.f("ck_verification_mail_status"), "verification_mail", type_="check")
    op.create_check_constraint(
        op.f("ck_verification_mail_status"),
        "verification_mail",
        "status IN ('pending', 'sent', 'accepted', 'cancelled', 'failed', 'uncertain')",
    )


def downgrade():
    # A development downgrade keeps terminal delivery records terminal.
    op.execute("UPDATE verification_mail SET status='sent' WHERE status='accepted'")
    op.execute("UPDATE verification_mail SET status='failed' WHERE status='uncertain'")
    op.drop_constraint(op.f("ck_verification_mail_status"), "verification_mail", type_="check")
    op.create_check_constraint(
        op.f("ck_verification_mail_status"),
        "verification_mail",
        "status IN ('pending', 'sent', 'cancelled', 'failed')",
    )
    op.drop_column("verification_mail", "acceptance_unknown")
    op.drop_column("verification_mail", "provider_message_id")
