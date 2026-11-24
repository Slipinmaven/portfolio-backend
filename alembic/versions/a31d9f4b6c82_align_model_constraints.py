"""align model constraints and add media tables

Revision ID: a31d9f4b6c82
Revises: 5908702d9b0c
Create Date: 2026-11-09
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a31d9f4b6c82"
down_revision: str | Sequence[str] | None = "5908702d9b0c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_constraint_if_exists(table: str, constraint: str) -> None:
    op.execute(
        sa.text(
            f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{constraint}"'
        )
    )


def _drop_index_if_exists(index: str) -> None:
    op.execute(sa.text(f'DROP INDEX IF EXISTS "{index}"'))


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM sessions
                GROUP BY refresh_token_hash
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'Cannot enforce unique session refresh_token_hash: duplicates exist';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM sessions s
                JOIN trusted_devices d ON d.id = s.trusted_device_id
                WHERE s.user_id <> d.user_id
            ) THEN
                RAISE EXCEPTION
                    'Cannot enforce session/trusted-device ownership: mismatched user IDs exist';
            END IF;
            IF EXISTS (
                SELECT 1 FROM sessions
                WHERE length(revocation_reason) > 100
            ) OR EXISTS (
                SELECT 1 FROM trusted_devices
                WHERE length(revocation_reason) > 100
            ) THEN
                RAISE EXCEPTION
                    'Cannot reduce revocation_reason to 100 characters: longer values exist';
            END IF;
            IF EXISTS (SELECT 1 FROM projects WHERE display_order < 0) THEN
                RAISE EXCEPTION
                    'Cannot enforce nonnegative project display_order: negative values exist';
            END IF;
        END
        $$;
        """
    )

    for table in ("audit_logs", "sessions", "users", "categories", "projects", "tags"):
        _drop_constraint_if_exists(table, op.f(f"uq_{table}_id"))

    _drop_constraint_if_exists("users", op.f("uq_users_email"))
    _drop_index_if_exists("ix_users_email")
    op.create_index(
        "uq_user_email",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )
    op.alter_column(
        "users",
        "first_name",
        existing_type=sa.String(length=50),
        type_=sa.String(length=100),
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "last_name",
        existing_type=sa.String(length=50),
        type_=sa.String(length=100),
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "is_active",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
        existing_nullable=False,
    )

    _drop_index_if_exists("ix_trusted_devices_device_token_hash")
    op.create_index(
        "uq_trusted_devices_token_hash",
        "trusted_devices",
        ["device_token_hash"],
        unique=True,
    )
    _drop_index_if_exists("ix_trusted_devices_user_id_expires_at")
    op.create_index(
        "uq_trusted_devices_user_id_id",
        "trusted_devices",
        ["user_id", "id"],
        unique=True,
    )
    op.create_index(
        "ix_trusted_devices_user_id",
        "trusted_devices",
        ["user_id"],
    )
    op.create_index(
        "ix_trusted_devices_unrevoked_user",
        "trusted_devices",
        ["user_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.alter_column(
        "trusted_devices",
        "revocation_reason",
        existing_type=sa.String(length=255),
        type_=sa.String(length=100),
        existing_nullable=True,
    )

    _drop_constraint_if_exists(
        "sessions",
        "fk_sessions_trusted_device_id_trusted_devices",
    )
    op.create_foreign_key(
        op.f("fk_sessions_user_trusted_device"),
        "sessions",
        "trusted_devices",
        ["user_id", "trusted_device_id"],
        ["user_id", "id"],
        ondelete="SET NULL (trusted_device_id)",
    )
    op.create_index(
        "uq_sessions_refresh_token_hash",
        "sessions",
        ["refresh_token_hash"],
        unique=True,
    )
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.create_index(
        "ix_sessions_unrevoked_user",
        "sessions",
        ["user_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.alter_column(
        "sessions",
        "revocation_reason",
        existing_type=sa.String(length=255),
        type_=sa.String(length=100),
        existing_nullable=True,
    )

    _drop_constraint_if_exists("audit_logs", op.f("fk_audit_logs_user_id_users"))
    op.create_foreign_key(
        op.f("fk_audit_logs_user_id_users"),
        "audit_logs",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_column("audit_logs", "updated_at")

    op.alter_column(
        "projects",
        "status",
        existing_type=sa.String(length=20),
        server_default=sa.text("'DRAFT'"),
        existing_nullable=False,
    )
    op.alter_column(
        "projects",
        "is_featured",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )
    op.create_check_constraint(
        op.f("ck_projects_ck_projects_display_order"),
        "projects",
        "display_order >= 0",
    )
    op.alter_column(
        "categories",
        "display_order",
        existing_type=sa.Integer(),
        server_default=sa.text("0"),
        existing_nullable=False,
    )
    op.alter_column(
        "categories",
        "is_active",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )
    op.alter_column(
        "tags",
        "is_active",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )

    op.create_table(
        "media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("alt_text", sa.String(length=500), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('IMAGE', 'DOCUMENT', 'VIDEO')",
            name=op.f("ck_media_kind"),
        ),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_media_size")),
        sa.CheckConstraint(
            "checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_media_checksum_format"),
        ),
        sa.CheckConstraint(
            "storage_key !~ '^/'",
            name=op.f("ck_media_key_relative"),
        ),
        sa.CheckConstraint(
            "(width IS NULL) = (height IS NULL)",
            name=op.f("ck_media_dimensions_pair"),
        ),
        sa.CheckConstraint(
            "width IS NULL OR (width > 0 AND height > 0 AND kind IN ('IMAGE', 'VIDEO'))",
            name=op.f("ck_media_dimensions_valid"),
        ),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR (duration_seconds > 0 AND kind = 'VIDEO')",
            name=op.f("ck_media_duration_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media")),
    )
    op.create_index(
        "uq_media_storage_key",
        "media",
        ["storage_key"],
        unique=True,
    )
    op.create_index("ix_media_checksum", "media", ["checksum_sha256"])
    op.create_index("ix_media_kind_created", "media", ["kind", "created_at"])

    op.create_table(
        "media_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=True),
        sa.Column(
            "display_order",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "url ~ '^https://'",
            name=op.f("ck_media_links_https"),
        ),
        sa.CheckConstraint(
            "display_order >= 0",
            name=op.f("ck_media_links_order"),
        ),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media.id"],
            name=op.f("fk_media_links_media_id_media"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_links")),
    )
    op.create_index(
        "uq_media_links_media_url",
        "media_links",
        ["media_id", "url"],
        unique=True,
    )
    op.create_index(
        "ix_media_links_media_order",
        "media_links",
        ["media_id", "display_order"],
    )

    op.create_table(
        "project_media",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column(
            "display_order",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("caption", sa.String(length=300), nullable=True),
        sa.CheckConstraint(
            "role IN ('COVER', 'GALLERY', 'INLINE', 'ATTACHMENT')",
            name=op.f("ck_project_media_role"),
        ),
        sa.CheckConstraint(
            "display_order >= 0",
            name=op.f("ck_project_media_order"),
        ),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media.id"],
            name=op.f("fk_project_media_media_id_media"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_media_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_id",
            "media_id",
            "role",
            name=op.f("pk_project_media"),
        ),
    )
    op.create_index(
        "ix_project_media_media_id",
        "project_media",
        ["media_id"],
    )
    op.create_index(
        "uq_project_media_cover",
        "project_media",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("role = 'COVER'"),
    )


def downgrade() -> None:
    op.drop_index("uq_project_media_cover", table_name="project_media")
    op.drop_index("ix_project_media_media_id", table_name="project_media")
    op.drop_table("project_media")
    op.drop_index("ix_media_links_media_order", table_name="media_links")
    op.drop_index("uq_media_links_media_url", table_name="media_links")
    op.drop_table("media_links")
    op.drop_index("ix_media_kind_created", table_name="media")
    op.drop_index("ix_media_checksum", table_name="media")
    op.drop_index("uq_media_storage_key", table_name="media")
    op.drop_table("media")

    op.drop_constraint(
        op.f("ck_projects_ck_projects_display_order"),
        "projects",
        type_="check",
    )
    op.alter_column(
        "tags",
        "is_active",
        existing_type=sa.Boolean(),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "categories",
        "is_active",
        existing_type=sa.Boolean(),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "categories",
        "display_order",
        existing_type=sa.Integer(),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "projects",
        "is_featured",
        existing_type=sa.Boolean(),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "projects",
        "status",
        existing_type=sa.String(length=20),
        server_default=None,
        existing_nullable=False,
    )

    op.add_column(
        "audit_logs",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.drop_constraint(
        op.f("fk_audit_logs_user_id_users"),
        "audit_logs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_audit_logs_user_id_users"),
        "audit_logs",
        "users",
        ["user_id"],
        ["id"],
    )

    op.drop_index("ix_sessions_unrevoked_user", table_name="sessions")
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index(
        "uq_sessions_refresh_token_hash",
        table_name="sessions",
    )
    op.drop_constraint(
        op.f("fk_sessions_user_trusted_device"),
        "sessions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_sessions_trusted_device_id_trusted_devices"),
        "sessions",
        "trusted_devices",
        ["trusted_device_id"],
        ["id"],
    )
    op.alter_column(
        "sessions",
        "revocation_reason",
        existing_type=sa.String(length=100),
        type_=sa.String(length=255),
        existing_nullable=True,
    )

    op.drop_index(
        "ix_trusted_devices_unrevoked_user",
        table_name="trusted_devices",
    )
    op.drop_index("ix_trusted_devices_user_id", table_name="trusted_devices")
    op.drop_index(
        "uq_trusted_devices_user_id_id",
        table_name="trusted_devices",
    )
    op.drop_index(
        "uq_trusted_devices_token_hash",
        table_name="trusted_devices",
    )
    op.create_index(
        "ix_trusted_devices_device_token_hash",
        "trusted_devices",
        ["device_token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_trusted_devices_user_id_expires_at",
        "trusted_devices",
        ["user_id", "expires_at"],
    )
    op.alter_column(
        "trusted_devices",
        "revocation_reason",
        existing_type=sa.String(length=100),
        type_=sa.String(length=255),
        existing_nullable=True,
    )

    op.drop_index("uq_user_email", table_name="users")
    op.create_unique_constraint(op.f("uq_users_email"), "users", ["email"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.alter_column(
        "users",
        "first_name",
        existing_type=sa.String(length=100),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "last_name",
        existing_type=sa.String(length=100),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "is_active",
        existing_type=sa.Boolean(),
        server_default=None,
        existing_nullable=False,
    )

    op.create_unique_constraint(op.f("uq_tags_id"), "tags", ["id"])
    op.create_unique_constraint(op.f("uq_projects_id"), "projects", ["id"])
    op.create_unique_constraint(op.f("uq_categories_id"), "categories", ["id"])
    op.create_unique_constraint(op.f("uq_users_id"), "users", ["id"])
    op.create_unique_constraint(op.f("uq_sessions_id"), "sessions", ["id"])
    op.create_unique_constraint(op.f("uq_audit_logs_id"), "audit_logs", ["id"])
