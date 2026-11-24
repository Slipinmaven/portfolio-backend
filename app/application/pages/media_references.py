from typing import Any
from uuid import UUID

from pydantic import TypeAdapter

from app.application.pages.blocks import HeroBlock, MarkdownBlock, PageBlock
from app.application.posts.markdown import inline_media_image_references

_BLOCKS_ADAPTER = TypeAdapter(list[PageBlock])


def collect_page_media_ids(blocks: list[PageBlock]) -> set[UUID]:
    media_ids: set[UUID] = set()
    for block in blocks:
        if isinstance(block, HeroBlock) and block.media_id is not None:
            media_ids.add(block.media_id)
        elif isinstance(block, MarkdownBlock):
            media_ids.update(
                media_id
                for _, media_id in inline_media_image_references(block.body)
            )
    return media_ids


def collect_page_media_ids_from_sections(
    sections: list[dict[str, Any]],
) -> set[UUID]:
    return collect_page_media_ids(_BLOCKS_ADAPTER.validate_python(sections))
