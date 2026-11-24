from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.application.errors import ConflictError, ResourceNotFoundError
from app.application.posts.markdown import inline_media_image_references
from app.application.posts.dto import (
    PostCreateDTO,
    PostListFilters,
    PostUpdateDTO,
)
from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.enums import (
    MediaKind,
    PostKind,
    PostMediaRole,
    PostStatus,
)
from app.infrastructure.database.models.media import Media
from app.infrastructure.database.models.post import Post
from app.infrastructure.database.models.post_media import PostMedia
from app.infrastructure.database.models.post_resource import PostResource
from app.infrastructure.database.models.project import Project
from app.infrastructure.database.models.resource import Resource
from app.infrastructure.database.unit_of_work.posts import PostsUnitOfWork

class PostService:
    def __init__(self, unit_of_work: PostsUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def list_posts(
        self,
        filters: PostListFilters,
    ) -> tuple[list[Post], int]:
        return await self._unit_of_work.posts.list_posts(
            offset=filters.offset,
            limit=filters.limit,
            kind=filters.kind,
            status=filters.status,
            published_only=filters.published_only,
            category_id=filters.category_id,
        )

    async def get_post_for_management(self, post_id: UUID) -> Post:
        post = await self._unit_of_work.posts.get_with_categories_by_id(post_id)
        if post is None:
            raise ResourceNotFoundError("Post not found.")
        return post

    async def get_published_post(self, kind: PostKind, slug: str) -> Post:
        post = await self._unit_of_work.posts.get_published_by_slug(kind, slug)
        if post is None:
            raise ResourceNotFoundError("Post not found.")
        return post

    async def create_post(
        self,
        data: PostCreateDTO,
        *,
        actor_id: UUID,
    ) -> Post:
        slug = data.slug.strip()
        if await self._unit_of_work.posts.get_by_slug(data.kind, slug):
            raise ConflictError("A post with this slug already exists for this kind.")

        category_ids = list(dict.fromkeys(data.category_ids))
        categories = await self._unit_of_work.categories.get_active_by_ids(
            category_ids
        )
        if len(categories) != len(category_ids):
            raise ResourceNotFoundError(
                "One or more selected categories do not exist or are inactive."
            )

        projects = await _load_projects(self._unit_of_work, data.project_ids)
        resources = await _load_resources(self._unit_of_work, data.resource_ids)
        inline_media = await _load_media(
            self._unit_of_work,
            _inline_image_ids(data.body),
            expected_kind=MediaKind.IMAGE,
        )
        attachments = await _load_media(
            self._unit_of_work,
            list(dict.fromkeys(data.attachment_media_ids)),
            expected_kind=MediaKind.DOCUMENT,
        )
        post = Post(
            kind=data.kind,
            title=data.title.strip(),
            slug=slug,
            summary=_normalize_summary(data.summary),
            body=data.body,
            status=PostStatus.DRAFT,
            categories=categories,
            projects=projects,
            resource_associations=_make_resource_associations(resources),
            media_associations=_make_media_associations(
                inline_media=inline_media,
                attachments=attachments,
            ),
        )
        try:
            await self._unit_of_work.posts.create(post)
            post = await self._unit_of_work.posts.get_with_categories_by_id(post.id)
            if post is None:
                raise RuntimeError("The created post could not be reloaded.")
            await self._unit_of_work.audit_logs.create(
                AuditLog(
                    user_id=actor_id,
                    action="post.created",
                    entity_type="post",
                    entity_id=post.id,
                    new_values={
                        "kind": _audit_value(post.kind),
                        "title": post.title,
                        "slug": post.slug,
                        "status": _audit_value(post.status),
                        "category_ids": [
                            str(category.id) for category in post.categories
                        ],
                        "project_ids": [
                            str(project.id) for project in post.projects
                        ],
                        "resource_ids": [
                            str(association.resource_id)
                            for association in post.resource_associations
                        ],
                        "attachment_media_ids": [
                            str(association.media_id)
                            for association in post.media_associations
                            if association.role == PostMediaRole.ATTACHMENT
                        ],
                    },
                    status="success",
                )
            )
            post_id = post.id
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            if await self._unit_of_work.posts.get_by_slug(data.kind, slug):
                raise ConflictError(
                    "A post with this slug already exists for this kind."
                ) from exc
            raise
        except BaseException:
            await self._unit_of_work.rollback()
            raise
        post = await self._unit_of_work.posts.get_with_categories_by_id(post_id)
        if post is None:
            raise RuntimeError("The created post could not be reloaded after commit.")
        return post

    async def update_post(
        self,
        post_id: UUID,
        data: PostUpdateDTO,
        *,
        actor_id: UUID,
    ) -> Post:
        post = await self.get_post_for_management(post_id)
        old_values: dict[str, object] = {}
        new_values: dict[str, object] = {}
        existing_kind = PostKind(post.kind)

        new_slug = (
            data.slug.strip()
            if "slug" in data.fields_set and data.slug is not None
            else post.slug
        )
        if new_slug != post.slug:
            if post.published_at is not None:
                raise ConflictError(
                    "A post slug cannot be changed after it has been published."
                )
            existing_post = await self._unit_of_work.posts.get_by_slug(
                existing_kind,
                new_slug,
            )
            if existing_post is not None and existing_post.id != post.id:
                raise ConflictError(
                    "A post with this slug already exists for this kind."
                )

        final_status = (
            data.status
            if "status" in data.fields_set and data.status is not None
            else PostStatus(post.status)
        )
        final_summary = (
            _normalize_summary(data.summary)
            if "summary" in data.fields_set
            else post.summary
        )

        categories = None
        if "category_ids" in data.fields_set:
            category_ids = list(dict.fromkeys(data.category_ids or ()))
            active_categories = await self._unit_of_work.categories.get_active_by_ids(
                category_ids
            )
            if len(active_categories) != len(category_ids):
                raise ResourceNotFoundError(
                    "One or more selected categories do not exist or are inactive."
                )
            inactive_categories = [
                category
                for category in post.categories
                if not category.is_active and category.id not in category_ids
            ]
            categories = [*active_categories, *inactive_categories]

        projects = None
        if "project_ids" in data.fields_set:
            projects = await _load_projects(
                self._unit_of_work,
                data.project_ids or (),
            )

        resource_associations = list(post.resource_associations)
        if "resource_ids" in data.fields_set:
            resources = await _load_resources(
                self._unit_of_work,
                data.resource_ids or (),
            )
            resource_associations = _make_resource_associations(resources)

        media_associations = list(post.media_associations)
        if "body" in data.fields_set:
            inline_media = await _load_media(
                self._unit_of_work,
                _inline_image_ids(data.body or ""),
                expected_kind=MediaKind.IMAGE,
            )
            media_associations = [
                association
                for association in media_associations
                if association.role != PostMediaRole.INLINE
            ]
            media_associations.extend(
                _make_media_associations(
                    inline_media=inline_media,
                    attachments=[],
                )
            )
        if "attachment_media_ids" in data.fields_set:
            attachments = await _load_media(
                self._unit_of_work,
                list(dict.fromkeys(data.attachment_media_ids or ())),
                expected_kind=MediaKind.DOCUMENT,
            )
            media_associations = [
                association
                for association in media_associations
                if association.role != PostMediaRole.ATTACHMENT
            ]
            media_associations.extend(
                _make_media_associations(
                    inline_media=[],
                    attachments=attachments,
                )
            )

        final_categories = categories if categories is not None else post.categories
        _validate_publication(
            kind=existing_kind,
            status=final_status,
            summary=final_summary,
            categories=final_categories,
            media_associations=media_associations,
            body=data.body if "body" in data.fields_set else post.body,
        )

        for field in ("title", "slug", "summary", "body"):
            if field not in data.fields_set:
                continue
            value = getattr(data, field)
            if field == "title" and isinstance(value, str):
                value = value.strip()
            elif field == "slug" and isinstance(value, str):
                value = new_slug
            elif field == "summary":
                value = _normalize_summary(value)
            old_value = getattr(post, field)
            if old_value == value:
                continue
            old_values[field] = old_value
            new_values[field] = value
            setattr(post, field, value)

        if categories is not None:
            previous_ids = [category.id for category in post.categories]
            updated_ids = [category.id for category in categories]
            if set(previous_ids) != set(updated_ids):
                old_values["category_ids"] = [
                    str(category_id) for category_id in previous_ids
                ]
                new_values["category_ids"] = [
                    str(category_id) for category_id in updated_ids
                ]
                post.categories = categories

        if projects is not None:
            previous_ids = [project.id for project in post.projects]
            updated_ids = [project.id for project in projects]
            if set(previous_ids) != set(updated_ids):
                old_values["project_ids"] = [
                    str(project_id) for project_id in previous_ids
                ]
                new_values["project_ids"] = [
                    str(project_id) for project_id in updated_ids
                ]
                post.projects = projects

        if "resource_ids" in data.fields_set:
            previous_resource_ids = [
                association.resource_id
                for association in post.resource_associations
            ]
            updated_resource_ids = [
                association.resource_id for association in resource_associations
            ]
            if previous_resource_ids != updated_resource_ids:
                old_values["resource_ids"] = [
                    str(resource_id) for resource_id in previous_resource_ids
                ]
                new_values["resource_ids"] = [
                    str(resource_id) for resource_id in updated_resource_ids
                ]
                post.resource_associations = resource_associations

        if (
            "body" in data.fields_set
            or "attachment_media_ids" in data.fields_set
        ):
            previous_attachments = [
                association.media_id
                for association in post.media_associations
                if association.role == PostMediaRole.ATTACHMENT
            ]
            updated_attachments = [
                association.media_id
                for association in media_associations
                if association.role == PostMediaRole.ATTACHMENT
            ]
            previous_inline = [
                association.media_id
                for association in post.media_associations
                if association.role == PostMediaRole.INLINE
            ]
            updated_inline = [
                association.media_id
                for association in media_associations
                if association.role == PostMediaRole.INLINE
            ]
            if previous_attachments != updated_attachments:
                old_values["attachment_media_ids"] = [
                    str(media_id) for media_id in previous_attachments
                ]
                new_values["attachment_media_ids"] = [
                    str(media_id) for media_id in updated_attachments
                ]
            if set(previous_inline) != set(updated_inline):
                old_values["inline_media_ids"] = [
                    str(media_id) for media_id in previous_inline
                ]
                new_values["inline_media_ids"] = [
                    str(media_id) for media_id in updated_inline
                ]
            post.media_associations = media_associations

        current_status = PostStatus(post.status)
        if current_status != final_status:
            old_values["status"] = _audit_value(current_status)
            new_values["status"] = _audit_value(final_status)
            post.status = final_status

        if final_status == PostStatus.PUBLISHED and post.published_at is None:
            post.published_at = datetime.now(timezone.utc)
            new_values["published_at"] = _audit_value(post.published_at)
        if final_status == PostStatus.ARCHIVED:
            if post.archived_at is None:
                post.archived_at = datetime.now(timezone.utc)
                new_values["archived_at"] = _audit_value(post.archived_at)
        elif post.archived_at is not None:
            old_values["archived_at"] = _audit_value(post.archived_at)
            post.archived_at = None
            new_values["archived_at"] = None

        slug_for_conflict_check = post.slug
        post_id = post.id
        try:
            if new_values:
                await self._unit_of_work.audit_logs.create(
                    AuditLog(
                        user_id=actor_id,
                        action="post.updated",
                        entity_type="post",
                        entity_id=post.id,
                        old_values=old_values,
                        new_values=new_values,
                        status="success",
                    )
                )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            existing_post = await self._unit_of_work.posts.get_by_slug(
                existing_kind,
                slug_for_conflict_check,
            )
            if existing_post is not None and existing_post.id != post_id:
                raise ConflictError(
                    "A post with this slug already exists for this kind."
                ) from exc
            raise
        except BaseException:
            await self._unit_of_work.rollback()
            raise
        post = await self._unit_of_work.posts.get_with_categories_by_id(post_id)
        if post is None:
            raise RuntimeError("The updated post could not be reloaded after commit.")
        return post


def _normalize_summary(summary: str | None) -> str | None:
    if summary is None:
        return None
    normalized = summary.strip()
    return normalized or None


def _validate_publication(
    *,
    kind: PostKind,
    status: PostStatus,
    summary: str | None,
    categories: list[object],
    media_associations: list[PostMedia],
    body: str,
) -> None:
    if status != PostStatus.PUBLISHED:
        return
    if kind == PostKind.ARTICLE and not summary:
        raise ConflictError("Articles need a summary before they can be published.")
    if kind == PostKind.ARTICLE and not categories:
        raise ConflictError(
            "Articles need at least one category before they can be published."
        )
    for association in media_associations:
        if association.role != PostMediaRole.INLINE:
            continue
        if association.media.kind != MediaKind.IMAGE:
            raise ConflictError("Inline post media must be an image.")
    if any(
        not alt_text.strip()
        for alt_text, _media_id in _inline_image_references(body)
    ):
        raise ConflictError("Add alternative text to every inline image before publishing.")


async def _load_projects(
    unit_of_work: PostsUnitOfWork,
    project_ids: tuple[UUID, ...] | list[UUID],
) -> list[Project]:
    unique_ids = list(dict.fromkeys(project_ids))
    projects = await unit_of_work.projects.get_by_ids(unique_ids)
    if len(projects) != len(unique_ids):
        raise ResourceNotFoundError("One or more selected projects do not exist.")
    project_by_id = {project.id: project for project in projects}
    return [project_by_id[project_id] for project_id in unique_ids]


async def _load_media(
    unit_of_work: PostsUnitOfWork,
    media_ids: list[UUID],
    *,
    expected_kind: MediaKind,
) -> list[Media]:
    unique_ids = list(dict.fromkeys(media_ids))
    media = await unit_of_work.media.get_by_ids(unique_ids)
    if len(media) != len(unique_ids):
        raise ResourceNotFoundError("One or more selected media items do not exist.")
    media_by_id = {item.id: item for item in media}
    ordered_media = [media_by_id[media_id] for media_id in unique_ids]
    if any(item.kind != expected_kind for item in ordered_media):
        raise ConflictError(
            "Inline images must use image files; attachments must be documents."
        )
    return ordered_media


async def _load_resources(
    unit_of_work: PostsUnitOfWork,
    resource_ids: tuple[UUID, ...] | list[UUID],
) -> list[Resource]:
    unique_ids = list(dict.fromkeys(resource_ids))
    resources = await unit_of_work.resources.get_by_ids(unique_ids)
    if len(resources) != len(unique_ids):
        raise ResourceNotFoundError("One or more selected resources do not exist.")
    resource_by_id = {resource.id: resource for resource in resources}
    return [resource_by_id[resource_id] for resource_id in unique_ids]


def _inline_image_ids(body: str) -> list[UUID]:
    return list(
        dict.fromkeys(
            media_id for _alt_text, media_id in _inline_image_references(body)
        )
    )


def _inline_image_references(body: str) -> list[tuple[str, UUID]]:
    return inline_media_image_references(body)


def _make_media_associations(
    *,
    inline_media: list[Media],
    attachments: list[Media],
) -> list[PostMedia]:
    inline_associations = [
        PostMedia(
            media_id=item.id,
            media=item,
            role=PostMediaRole.INLINE,
            display_order=index,
        )
        for index, item in enumerate(inline_media)
    ]
    attachment_associations = [
        PostMedia(
            media_id=item.id,
            media=item,
            role=PostMediaRole.ATTACHMENT,
            display_order=index,
        )
        for index, item in enumerate(attachments)
    ]
    return [*inline_associations, *attachment_associations]


def _make_resource_associations(
    resources: list[Resource],
) -> list[PostResource]:
    return [
        PostResource(
            resource_id=resource.id,
            resource=resource,
            display_order=index,
        )
        for index, resource in enumerate(resources)
    ]


def _audit_value(value: object) -> object:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
