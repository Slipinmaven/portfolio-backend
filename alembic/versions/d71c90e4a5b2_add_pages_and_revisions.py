"""add pages and revision snapshots

Revision ID: d71c90e4a5b2
Revises: c51e7b9f4a20
Create Date: 2026-11-19
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d71c90e4a5b2"
down_revision: str | Sequence[str] | None = (
    "c51e7b9f4a20",
    "8b3c2d7f4a19",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("system_key", sa.String(length=20), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'",
            name=op.f("ck_pages_slug_format"),
        ),
        sa.CheckConstraint(
            "system_key IS NULL OR system_key IN ('HOME', 'ABOUT', 'CONTACT')",
            name=op.f("ck_pages_system_key"),
        ),
        sa.CheckConstraint(
            "system_key IS NULL OR slug = lower(system_key)",
            name=op.f("ck_pages_system_slug_locked"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')",
            name=op.f("ck_pages_status"),
        ),
        sa.CheckConstraint(
            "status <> 'PUBLISHED' OR published_at IS NOT NULL",
            name=op.f("ck_pages_published_has_date"),
        ),
        sa.CheckConstraint(
            "(status = 'ARCHIVED') = (archived_at IS NOT NULL)",
            name=op.f("ck_pages_archived_pair"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pages")),
        sa.UniqueConstraint("slug", name=op.f("uq_pages_slug")),
        sa.UniqueConstraint("system_key", name=op.f("uq_pages_system_key")),
    )
    op.create_index("ix_pages_status", "pages", ["status"])

    op.create_table(
        "page_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=12), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=True),
        sa.Column(
            "sections",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "schema_version",
            sa.SmallInteger(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("change_note", sa.String(length=300), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision_number > 0",
            name=op.f("ck_page_revisions_number_positive"),
        ),
        sa.CheckConstraint(
            "state IN ('DRAFT', 'PUBLISHED', 'SUPERSEDED')",
            name=op.f("ck_page_revisions_state"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(sections) = 'array'",
            name=op.f("ck_page_revisions_sections_array"),
        ),
        sa.CheckConstraint(
            "(state = 'DRAFT' AND published_at IS NULL AND superseded_at IS NULL) "
            "OR (state = 'PUBLISHED' AND published_at IS NOT NULL "
            "AND superseded_at IS NULL) "
            "OR (state = 'SUPERSEDED' AND published_at IS NOT NULL "
            "AND superseded_at IS NOT NULL)",
            name=op.f("ck_page_revisions_state_dates"),
        ),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["pages.id"],
            name=op.f("fk_page_revisions_page_id_pages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_page_revisions")),
    )
    op.create_index(
        "uq_page_revisions_page_number",
        "page_revisions",
        ["page_id", "revision_number"],
        unique=True,
    )
    op.create_index(
        "uq_page_revisions_one_draft",
        "page_revisions",
        ["page_id"],
        unique=True,
        postgresql_where=sa.text("state = 'DRAFT'"),
    )
    op.create_index(
        "uq_page_revisions_one_published",
        "page_revisions",
        ["page_id"],
        unique=True,
        postgresql_where=sa.text("state = 'PUBLISHED'"),
    )

    op.create_table(
        "page_media",
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media.id"],
            name=op.f("fk_page_media_media_id_media"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["pages.id"],
            name=op.f("fk_page_media_page_id_pages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "page_id",
            "media_id",
            name=op.f("pk_page_media"),
        ),
    )
    op.create_index("ix_page_media_media_id", "page_media", ["media_id"])

    _seed_system_pages()


def _seed_system_pages() -> None:
    now = datetime.now(timezone.utc)
    pages = sa.table(
        "pages",
        sa.column("id", sa.Uuid()),
        sa.column("slug", sa.String()),
        sa.column("system_key", sa.String()),
        sa.column("status", sa.String()),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("archived_at", sa.DateTime(timezone=True)),
    )
    revisions = sa.table(
        "page_revisions",
        sa.column("id", sa.Uuid()),
        sa.column("page_id", sa.Uuid()),
        sa.column("revision_number", sa.Integer()),
        sa.column("state", sa.String()),
        sa.column("title", sa.String()),
        sa.column("summary", sa.String()),
        sa.column("schema_version", sa.SmallInteger()),
        sa.column("change_note", sa.String()),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("superseded_at", sa.DateTime(timezone=True)),
    )
    system_pages = [
        ("HOME", "home", "Home"),
        ("ABOUT", "about", "About"),
        ("CONTACT", "contact", "Contact"),
    ]
    page_rows = []
    revision_rows = []
    for key, slug, title in system_pages:
        page_id = uuid5(NAMESPACE_URL, f"portfolio-system-page:{key}")
        revision_rows.append(
            {
                "id": uuid5(NAMESPACE_URL, f"portfolio-system-page-revision:{key}:1"),
                "page_id": page_id,
                "revision_number": 1,
                "state": "PUBLISHED",
                "title": title,
                "summary": None,
                "schema_version": 1,
                "change_note": "Initial system page.",
                "published_at": now,
                "superseded_at": None,
            }
        )
        page_rows.append(
            {
                "id": page_id,
                "slug": slug,
                "system_key": key,
                "status": "PUBLISHED",
                "published_at": now,
                "archived_at": None,
            }
        )
    op.bulk_insert(pages, page_rows)
    op.bulk_insert(revisions, revision_rows)


def downgrade() -> None:
    op.drop_index("ix_page_media_media_id", table_name="page_media")
    op.drop_table("page_media")
    op.drop_index(
        "uq_page_revisions_one_published",
        table_name="page_revisions",
    )
    op.drop_index(
        "uq_page_revisions_one_draft",
        table_name="page_revisions",
    )
    op.drop_index(
        "uq_page_revisions_page_number",
        table_name="page_revisions",
    )
    op.drop_table("page_revisions")
    op.drop_index("ix_pages_status", table_name="pages")
    op.drop_table("pages")
