"""add WhatsApp site link platform

Revision ID: c84b7d2a9510
Revises: f2a9c1d8e047
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c84b7d2a9510"
down_revision: str | Sequence[str] | None = "f2a9c1d8e047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_site_links_platform"),
        "site_links",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_site_links_platform"),
        "site_links",
        "platform IN ('GITHUB', 'LINKEDIN', 'X', 'YOUTUBE', 'TIKTOK', "
        "'INSTAGRAM', 'BLUESKY', 'MASTODON', 'EMAIL', 'WHATSAPP', 'OTHER')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_whatsapp_links = bind.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM site_links WHERE platform = 'WHATSAPP')")
    )
    if has_whatsapp_links:
        raise RuntimeError(
            "Cannot remove WhatsApp while site_links contains WhatsApp rows."
        )

    op.drop_constraint(
        op.f("ck_site_links_platform"),
        "site_links",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_site_links_platform"),
        "site_links",
        "platform IN ('GITHUB', 'LINKEDIN', 'X', 'YOUTUBE', 'TIKTOK', "
        "'INSTAGRAM', 'BLUESKY', 'MASTODON', 'EMAIL', 'OTHER')",
    )
