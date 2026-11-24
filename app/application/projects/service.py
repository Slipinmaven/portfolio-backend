from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.application.errors import ConflictError, ResourceNotFoundError
from app.application.projects.dto import (
    ProjectCreateDTO,
    ProjectListFilters,
    ProjectUpdateDTO,
)
from app.application.posts.markdown import inline_media_references
from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.enums import (
    MediaKind,
    ProjectMediaRole,
    ProjectStatus,
)
from app.infrastructure.database.models.project import Project
from app.infrastructure.database.models.project_media import ProjectMedia
from app.infrastructure.database.models.project_resource import ProjectResource
from app.infrastructure.database.models.resource import Resource
from app.infrastructure.database.unit_of_work.project import ProjectUnitOfWork


class ProjectService:
    def __init__(self, unit_of_work: ProjectUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def list_projects(
        self,
        filters: ProjectListFilters,
    ) -> tuple[list[Project], int]:
        return await self._unit_of_work.projects.list_projects(
            offset=filters.offset,
            limit=filters.limit,
            status=filters.status,
            development_status=filters.development_status,
            is_featured=filters.is_featured,
            category_id=filters.category_id,
            tag_id=filters.tag_id,
            active_catalog_only=filters.active_catalog_only,
        )

    async def get_project_covers(
        self,
        project_ids: list[UUID],
    ) -> dict[UUID, ProjectMedia]:
        return await self._unit_of_work.projects.get_project_covers(project_ids)

    async def get_published_project(self, slug: str) -> Project:
        project = await self._unit_of_work.projects.get_published_by_slug(slug)
        if project is None:
            raise ResourceNotFoundError("Project not found.")
        return project

    async def get_project_for_management(self, project_id: UUID) -> Project:
        project = await self._unit_of_work.projects.get_with_associations_by_id(
            project_id
        )
        if project is None:
            raise ResourceNotFoundError("Project not found.")
        return project

    async def update_project(
        self,
        project_id: UUID,
        data: ProjectUpdateDTO,
        *,
        actor_id: UUID,
    ) -> Project:
        project = await self.get_project_for_management(project_id)
        old_values: dict[str, object] = {}
        new_values: dict[str, object] = {}

        new_slug = (
            data.slug.strip()
            if "slug" in data.fields_set and data.slug is not None
            else project.slug
        )
        if new_slug != project.slug:
            existing_project = await self._unit_of_work.projects.get_by_slug(new_slug)
            if existing_project is not None and existing_project.id != project.id:
                raise ConflictError("A project with this slug already exists.")

        final_status = data.status if "status" in data.fields_set else project.status
        final_published_at = (
            data.published_at
            if "published_at" in data.fields_set
            else project.published_at
        )
        final_archived_at = (
            data.archived_at
            if "archived_at" in data.fields_set
            else project.archived_at
        )
        overview_submitted = "overview" in data.fields_set
        if final_status == ProjectStatus.PUBLISHED and final_published_at is None:
            raise ConflictError("published_at is required for published projects.")
        if (final_status == ProjectStatus.ARCHIVED) != (
            final_archived_at is not None
        ):
            raise ConflictError(
                "archived_at must be set exactly when status is ARCHIVED."
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
                for category in project.categories
                if not category.is_active and category.id not in category_ids
            ]
            categories = [*active_categories, *inactive_categories]

        tags = None
        if "tag_ids" in data.fields_set:
            tag_ids = list(dict.fromkeys(data.tag_ids or ()))
            active_tags = await self._unit_of_work.tags.get_active_by_ids(tag_ids)
            if len(active_tags) != len(tag_ids):
                raise ResourceNotFoundError(
                    "One or more selected tags do not exist or are inactive."
                )
            inactive_tags = [
                tag
                for tag in project.tags
                if not tag.is_active and tag.id not in tag_ids
            ]
            tags = [*active_tags, *inactive_tags]

        resource_associations = list(project.resource_associations)
        if "resource_ids" in data.fields_set:
            resources = await _load_resources(
                self._unit_of_work,
                data.resource_ids or (),
            )
            resource_associations = _make_resource_associations(resources)

        final_categories = categories if categories is not None else project.categories
        if final_status == ProjectStatus.PUBLISHED and not final_categories:
            raise ConflictError(
                "Published projects must be assigned to at least one category."
            )
        media_associations = list(project.media_associations)
        if overview_submitted or final_status == ProjectStatus.PUBLISHED:
            media_associations = [
                association
                for association in media_associations
                if association.role != ProjectMediaRole.INLINE
            ]
            overview = data.overview if overview_submitted else project.overview
            media_associations.extend(
                await _make_inline_media_associations(
                    self._unit_of_work,
                    project.id,
                    overview or "",
                    published=final_status == ProjectStatus.PUBLISHED,
                    existing=project.media_associations,
                )
            )
        if final_status == ProjectStatus.PUBLISHED:
            for association in media_associations:
                media = association.media
                if (
                    association.role != ProjectMediaRole.INLINE
                    and media.kind == MediaKind.IMAGE
                    and not media.alt_text
                ):
                    raise ConflictError(
                        "Add alternative text to every project image before publishing."
                    )

        for field in (
            "title",
            "slug",
            "short_description",
            "development_status",
            "display_order",
            "github_url",
            "demo_url",
            "overview",
            "status",
            "published_at",
            "archived_at",
            "is_featured",
        ):
            if field not in data.fields_set:
                continue
            value = getattr(data, field)
            if field in {"title", "slug", "short_description"} and isinstance(
                value, str
            ):
                value = value.strip()
            if field == "slug":
                value = new_slug
            old_value = getattr(project, field)
            if old_value == value:
                continue
            old_values[field] = _audit_value(old_value)
            new_values[field] = _audit_value(value)
            setattr(project, field, value)

        if overview_submitted or final_status == ProjectStatus.PUBLISHED:
            project.media_associations = media_associations

        if categories is not None:
            previous_ids = [category.id for category in project.categories]
            updated_ids = [category.id for category in categories]
            if set(previous_ids) != set(updated_ids):
                old_values["category_ids"] = [str(category_id) for category_id in previous_ids]
                new_values["category_ids"] = [str(category_id) for category_id in updated_ids]
                project.categories = categories

        if tags is not None:
            previous_ids = [tag.id for tag in project.tags]
            updated_ids = [tag.id for tag in tags]
            if set(previous_ids) != set(updated_ids):
                old_values["tag_ids"] = [str(tag_id) for tag_id in previous_ids]
                new_values["tag_ids"] = [str(tag_id) for tag_id in updated_ids]
                project.tags = tags

        if "resource_ids" in data.fields_set:
            previous_resource_ids = [
                association.resource_id
                for association in project.resource_associations
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
                project.resource_associations = resource_associations


        updated_slug = project.slug
        try:
            if new_values:
                await self._unit_of_work.audit_logs.create(
                    AuditLog(
                        user_id=actor_id,
                        action="project.updated",
                        entity_type="project",
                        entity_id=project.id,
                        old_values=old_values,
                        new_values=new_values,
                        status="success",
                    )
                )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            if "slug" in data.fields_set and await self._unit_of_work.projects.get_by_slug(
                updated_slug
            ):
                raise ConflictError(
                    "A project with this slug already exists."
                ) from exc
            raise
        except BaseException:
            await self._unit_of_work.rollback()
            raise

        updated_project = await self._unit_of_work.projects.get_with_associations_by_id(
            project.id
        )
        if updated_project is None:
            raise RuntimeError("The updated project could not be reloaded.")
        return updated_project

    async def create_project(
        self,
        data: ProjectCreateDTO,
        *,
        actor_id: UUID,
    ) -> Project:
        slug = data.slug.strip()
        if await self._unit_of_work.projects.get_by_slug(slug):
            raise ConflictError("A project with this slug already exists.")

        category_ids = list(dict.fromkeys(data.category_ids))
        tag_ids = list(dict.fromkeys(data.tag_ids))
        categories = await self._unit_of_work.categories.get_active_by_ids(
            category_ids
        )
        tags = await self._unit_of_work.tags.get_active_by_ids(tag_ids)
        resources = await _load_resources(self._unit_of_work, data.resource_ids)
        if len(categories) != len(category_ids):
            raise ResourceNotFoundError(
                "One or more selected categories do not exist or are inactive."
            )
        if len(tags) != len(tag_ids):
            raise ResourceNotFoundError(
                "One or more selected tags do not exist or are inactive."
            )
        if data.status == ProjectStatus.PUBLISHED and not categories:
            raise ConflictError(
                "Published projects must be assigned to at least one category."
            )
        media_associations = await _make_inline_media_associations(
            self._unit_of_work,
            None,
            data.overview or "",
            published=data.status == ProjectStatus.PUBLISHED,
        )

        project = Project(
            title=data.title.strip(),
            slug=slug,
            short_description=data.short_description.strip(),
            development_status=data.development_status,
            display_order=data.display_order,
            github_url=data.github_url,
            demo_url=data.demo_url,
            overview=data.overview,
            status=data.status,
            published_at=data.published_at,
            archived_at=data.archived_at,
            is_featured=data.is_featured,
            categories=categories,
            tags=tags,
            media_associations=media_associations,
            resource_associations=_make_resource_associations(resources),
        )

        try:
            await self._unit_of_work.projects.create(project)
            project = await self._unit_of_work.projects.get_with_associations_by_id(
                project.id
            )
            if project is None:
                raise RuntimeError("The created project could not be reloaded.")
            await self._unit_of_work.audit_logs.create(
                AuditLog(
                    user_id=actor_id,
                    action="project.created",
                    entity_type="project",
                    entity_id=project.id,
                    new_values={
                        "title": project.title,
                        "slug": project.slug,
                        "status": getattr(project.status, "value", project.status),
                        "development_status": getattr(
                            project.development_status,
                            "value",
                            project.development_status,
                        ),
                        "category_ids": [str(category.id) for category in categories],
                        "tag_ids": [str(tag.id) for tag in tags],
                        "resource_ids": [
                            str(association.resource_id)
                            for association in project.resource_associations
                        ],
                    },
                    status="success",
                )
            )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            if await self._unit_of_work.projects.get_by_slug(slug):
                raise ConflictError("A project with this slug already exists.") from exc
            raise
        except BaseException:
            await self._unit_of_work.rollback()
            raise

        return project


def _audit_value(value: object) -> object:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


async def _load_resources(
    unit_of_work: ProjectUnitOfWork,
    resource_ids: tuple[UUID, ...] | list[UUID],
) -> list[Resource]:
    unique_ids = list(dict.fromkeys(resource_ids))
    resources = await unit_of_work.resources.get_by_ids(unique_ids)
    if len(resources) != len(unique_ids):
        raise ResourceNotFoundError("One or more selected resources do not exist.")
    resource_by_id = {resource.id: resource for resource in resources}
    return [resource_by_id[resource_id] for resource_id in unique_ids]


def _make_resource_associations(
    resources: list[Resource],
) -> list[ProjectResource]:
    return [
        ProjectResource(
            resource_id=resource.id,
            resource=resource,
            display_order=index,
        )
        for index, resource in enumerate(resources)
    ]


async def _make_inline_media_associations(
    unit_of_work: ProjectUnitOfWork,
    project_id: UUID | None,
    overview: str,
    *,
    published: bool,
    existing: list[ProjectMedia] | None = None,
) -> list[ProjectMedia]:
    references = inline_media_references(overview)
    if published:
        if any(
            kind == "IMAGE" and not label.strip()
            for kind, label, _media_id in references
        ):
            raise ConflictError(
                "Add alternative text to every inline image before publishing."
            )
        if any(
            kind in {"VIDEO", "DOCUMENT"} and not label.strip()
            for kind, label, _media_id in references
        ):
            raise ConflictError(
                "Add descriptive text to every inline video and document link "
                "before publishing."
            )
    media_ids = list(dict.fromkeys(media_id for _kind, _label, media_id in references))
    media = await unit_of_work.media.get_by_ids(media_ids)
    if len(media) != len(media_ids):
        raise ResourceNotFoundError("One or more selected media items do not exist.")
    media_by_id = {item.id: item for item in media}
    existing_by_id = {
        association.media_id: association
        for association in existing or ()
        if association.role == ProjectMediaRole.INLINE
    }

    expected_kinds = {
        "IMAGE": MediaKind.IMAGE,
        "VIDEO": MediaKind.VIDEO,
        "DOCUMENT": MediaKind.DOCUMENT,
    }
    for kind, _label, media_id in references:
        if media_by_id[media_id].kind != expected_kinds[kind]:
            raise ConflictError(
                f"Inline project {kind.lower()} references must use "
                f"{expected_kinds[kind].value.lower()} files."
            )
    ordered_media = [media_by_id[media_id] for media_id in media_ids]

    associations: list[ProjectMedia] = []
    for display_order, (media_id, item) in enumerate(
        zip(media_ids, ordered_media, strict=True)
    ):
        association = existing_by_id.get(media_id)
        if association is None:
            association = ProjectMedia(
                project_id=project_id,
                media_id=media_id,
                media=item,
                role=ProjectMediaRole.INLINE,
                display_order=display_order,
            )
        else:
            association.display_order = display_order
        associations.append(association)

    return associations
