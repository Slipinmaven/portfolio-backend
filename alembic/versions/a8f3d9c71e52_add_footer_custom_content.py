"""add custom footer content

Revision ID: a8f3d9c71e52
Revises: d8a4c6f2917b
Create Date: 2026-11-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a8f3d9c71e52"
down_revision: str | Sequence[str] | None = "d8a4c6f2917b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "navigation_items",
        sa.Column("custom_target", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "navigation_items",
        sa.Column("content_text", sa.Text(), nullable=True),
    )
    op.drop_constraint(
        op.f("ck_navigation_items_link_type"),
        "navigation_items",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_navigation_items_one_target"),
        "navigation_items",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_navigation_items_link_type"),
        "navigation_items",
        "link_type IN ('NONE', 'PAGE', 'ROUTE', 'PROJECT', 'POST', 'CATEGORY', "
        "'EXTERNAL', 'EMAIL', 'PHONE', 'TEXT')",
    )
    op.create_check_constraint(
        op.f("ck_navigation_items_one_target"),
        "navigation_items",
        "num_nonnulls(page_id, project_id, post_id, category_id, route_key, "
        "custom_target, content_text) = "
        "CASE WHEN link_type = 'NONE' THEN 0 ELSE 1 END",
    )
    op.create_check_constraint(
        op.f("ck_navigation_items_footer_content_only"),
        "navigation_items",
        "link_type NOT IN ('EXTERNAL', 'EMAIL', 'PHONE', 'TEXT') "
        "OR menu = 'FOOTER'",
    )
    op.create_check_constraint(
        op.f("ck_navigation_items_custom_target_type"),
        "navigation_items",
        "custom_target IS NULL OR link_type IN ('EXTERNAL', 'EMAIL', 'PHONE')",
    )
    op.create_check_constraint(
        op.f("ck_navigation_items_content_text_type"),
        "navigation_items",
        "content_text IS NULL OR link_type = 'TEXT'",
    )
    op.create_check_constraint(
        op.f("ck_navigation_items_external_target"),
        "navigation_items",
        "link_type <> 'EXTERNAL' OR custom_target ~ '^https://[^[:space:]]+$'",
    )
    op.create_check_constraint(
        op.f("ck_navigation_items_email_target"),
        "navigation_items",
        "link_type <> 'EMAIL' OR custom_target ~ '^[^[:space:]@]+@[^[:space:]@]+\\.[^[:space:]@]+$'",
    )
    op.create_check_constraint(
        op.f("ck_navigation_items_phone_target"),
        "navigation_items",
        "link_type <> 'PHONE' OR custom_target ~ '^\\+?[0-9][0-9 ().-]{5,24}$'",
    )
    op.create_check_constraint(
        op.f("ck_navigation_items_text_content"),
        "navigation_items",
        "link_type <> 'TEXT' OR "
        "(length(btrim(content_text)) BETWEEN 1 AND 1000)",
    )


def downgrade() -> None:
    for constraint in (
        "footer_content_only",
        "custom_target_type",
        "content_text_type",
        "external_target",
        "email_target",
        "phone_target",
        "text_content",
        "link_type",
        "one_target",
    ):
        op.drop_constraint(
            op.f(f"ck_navigation_items_{constraint}"),
            "navigation_items",
            type_="check",
        )
    op.drop_column("navigation_items", "content_text")
    op.drop_column("navigation_items", "custom_target")
    op.create_check_constraint(
        op.f("ck_navigation_items_link_type"),
        "navigation_items",
        "link_type IN ('NONE', 'PAGE', 'ROUTE', 'PROJECT', 'POST', 'CATEGORY')",
    )
    op.create_check_constraint(
        op.f("ck_navigation_items_one_target"),
        "navigation_items",
        "num_nonnulls(page_id, project_id, post_id, category_id, route_key) = "
        "CASE WHEN link_type = 'NONE' THEN 0 ELSE 1 END",
    )
