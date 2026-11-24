import re
from collections.abc import Callable
from html import escape
from typing import Literal, cast
from uuid import UUID

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML

_MEDIA_REFERENCE_SOURCE = re.compile(
    r"^media:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$"
)
_MEDIA_IMAGE_LAYOUT = re.compile(
    r"^media-layout:width=(\d{1,3});align=(left|center|right)$"
)
_INLINE_VIDEO_TITLE = "media-video"
_TEXT_ALIGNMENT_OPEN = re.compile(
    r'^ {0,3}:::textAlignment\s+\{alignment="(left|center|right)"\}\s*$'
)
_TEXT_ALIGNMENT_CLOSE = re.compile(r"^ {0,3}:::\s*$")
_CODE_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_CODE_FENCE_CLOSE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")


def inline_media_image_references(body: str) -> list[tuple[str, UUID]]:
    return [
        (label, media_id)
        for kind, label, media_id in inline_media_references(body)
        if kind == "IMAGE"
    ]


def inline_media_references(
    body: str,
) -> list[tuple[Literal["IMAGE", "VIDEO", "DOCUMENT"], str, UUID]]:
    references: list[tuple[Literal["IMAGE", "VIDEO", "DOCUMENT"], str, UUID]] = []
    for token in MarkdownIt("commonmark").parse(body):
        if token.type != "inline" or token.children is None:
            continue
        for index, child in enumerate(token.children):
            if child.type == "image":
                source = child.attrGet("src")
                if not isinstance(source, str):
                    continue
                match = _MEDIA_REFERENCE_SOURCE.fullmatch(source)
                if match is None:
                    continue
                title = child.attrGet("title")
                kind: Literal["IMAGE", "VIDEO"] = (
                    "VIDEO" if title == _INLINE_VIDEO_TITLE else "IMAGE"
                )
                references.append((kind, child.content, UUID(match.group(1))))
            elif child.type == "link_open":
                href = child.attrGet("href")
                match = (
                    _MEDIA_REFERENCE_SOURCE.fullmatch(href)
                    if isinstance(href, str)
                    else None
                )
                if match is None:
                    continue
                label_parts: list[str] = []
                for link_child in token.children[index + 1 :]:
                    if link_child.type == "link_close":
                        break
                    if link_child.type in {"text", "text_special", "code_inline"}:
                        label_parts.append(link_child.content)
                references.append(
                    ("DOCUMENT", "".join(label_parts), UUID(match.group(1)))
                )
    return references


def render_markdown(
    body: str,
    *,
    media_url_resolver: Callable[[UUID], str | None] | None = None,
    media_video_url_resolver: Callable[[UUID], str | None] | None = None,
    media_download_url_resolver: Callable[[UUID], str | None] | None = None,
) -> str:
    aligned_block = _find_text_alignment_block(body)
    if aligned_block is None:
        return _render_markdown_source(
            body,
            media_url_resolver=media_url_resolver,
            media_video_url_resolver=media_video_url_resolver,
            media_download_url_resolver=media_download_url_resolver,
        )

    start, end, alignment, content = aligned_block
    before_html = render_markdown(
        body[:start],
        media_url_resolver=media_url_resolver,
        media_video_url_resolver=media_video_url_resolver,
        media_download_url_resolver=media_download_url_resolver,
    )
    content_html = render_markdown(
        content,
        media_url_resolver=media_url_resolver,
        media_video_url_resolver=media_video_url_resolver,
        media_download_url_resolver=media_download_url_resolver,
    )
    after_html = render_markdown(
        body[end:],
        media_url_resolver=media_url_resolver,
        media_video_url_resolver=media_video_url_resolver,
        media_download_url_resolver=media_download_url_resolver,
    )
    return (
        f"{before_html}<div style=\"text-align: {alignment};\">\n"
        f"{content_html}</div>\n{after_html}"
    )


def _render_markdown_source(
    body: str,
    *,
    media_url_resolver: Callable[[UUID], str | None] | None = None,
    media_video_url_resolver: Callable[[UUID], str | None] | None = None,
    media_download_url_resolver: Callable[[UUID], str | None] | None = None,
) -> str:
    renderer = MarkdownIt(
        "commonmark",
        {
            "html": False,
            "linkify": False,
            "typographer": False,
        },
    )

    html_renderer = cast(RendererHTML, renderer.renderer)
    default_image_rule = html_renderer.rules.get("image")

    def render_image(_renderer: RendererHTML, tokens, index, options, env):
        token = tokens[index]
        # Escaped punctuation is still literal text in an image's alt attribute.
        for alt_token in token.children or ():
            if alt_token.type == "text_special":
                alt_token.type = "text"
        source_value = token.attrGet("src")
        source = source_value if isinstance(source_value, str) else ""
        title_value = token.attrGet("title")
        title = title_value if isinstance(title_value, str) else ""
        match = _MEDIA_REFERENCE_SOURCE.fullmatch(source)
        if title == _INLINE_VIDEO_TITLE:
            media_url = (
                media_video_url_resolver(UUID(match.group(1)))
                if match is not None and media_video_url_resolver is not None
                else None
            )
            if media_url is None:
                return '<span class="media-placeholder">Video unavailable</span>'
            caption = (
                f"<figcaption>{escape(token.content)}</figcaption>"
                if token.content.strip()
                else ""
            )
            return (
                '<figure class="inline-media-video-frame">'
                '<video class="inline-media-video" controls preload="metadata" '
                f'aria-label="{escape(token.content, quote=True)}" '
                f'src="{escape(media_url, quote=True)}"></video>'
                f"{caption}</figure>"
            )
        layout_match = _MEDIA_IMAGE_LAYOUT.fullmatch(title)
        if layout_match:
            width = int(layout_match.group(1))
            alignment = layout_match.group(2)
            if token.attrs is not None:
                token.attrs.pop("title", None)
            if 20 <= width <= 100:
                margin_left, margin_right = {
                    "left": ("0", "auto"),
                    "center": ("auto", "auto"),
                    "right": ("auto", "0"),
                }[alignment]
                token.attrSet(
                    "style",
                    f"width: {width}%; display: block; margin-left: "
                    f"{margin_left}; margin-right: {margin_right}; height: auto;",
                )
        if match:
            media_url = (
                media_url_resolver(UUID(match.group(1)))
                if media_url_resolver is not None
                else None
            )
            if media_url is None:
                return '<span class="media-placeholder">Image unavailable</span>'
            token.attrSet("src", media_url)
        if default_image_rule is not None:
            return default_image_rule(tokens, index, options, env)
        return _renderer.renderToken(tokens, index, options, env)

    default_link_open_rule = html_renderer.rules.get("link_open")

    def render_link_open(_renderer: RendererHTML, tokens, index, options, env):
        token = tokens[index]
        href_value = token.attrGet("href")
        match = (
            _MEDIA_REFERENCE_SOURCE.fullmatch(href_value)
            if isinstance(href_value, str)
            else None
        )
        if match is not None:
            media_url = (
                media_download_url_resolver(UUID(match.group(1)))
                if media_download_url_resolver is not None
                else None
            )
            if media_url is None:
                if token.attrs is not None:
                    token.attrs.pop("href", None)
                token.attrSet("aria-disabled", "true")
            else:
                token.attrSet("href", media_url)
                token.attrSet("download", "")
        if default_link_open_rule is not None:
            return default_link_open_rule(tokens, index, options, env)
        return _renderer.renderToken(tokens, index, options, env)

    renderer.add_render_rule("image", render_image)
    renderer.add_render_rule("link_open", render_link_open)
    return renderer.render(body)


def _find_text_alignment_block(body: str) -> tuple[int, int, str, str] | None:
    lines = body.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    fence: tuple[str, int] | None = None
    for index, line in enumerate(lines):
        source_line = line.rstrip("\r\n")
        if fence is not None:
            if _closes_code_fence(source_line, fence):
                fence = None
            continue

        fence = _opens_code_fence(source_line)
        if fence is not None:
            continue

        match = _TEXT_ALIGNMENT_OPEN.fullmatch(source_line)
        if match is None:
            continue
        closing_index = _find_text_alignment_close(lines, index)
        if closing_index is None:
            continue

        return (
            offsets[index],
            offsets[closing_index + 1],
            match.group(1),
            body[offsets[index + 1] : offsets[closing_index]],
        )
    return None


def _find_text_alignment_close(
    lines: list[str],
    opening_index: int,
) -> int | None:
    depth = 1
    fence: tuple[str, int] | None = None
    for index in range(opening_index + 1, len(lines)):
        source_line = lines[index].rstrip("\r\n")
        if fence is not None:
            if _closes_code_fence(source_line, fence):
                fence = None
            continue

        fence = _opens_code_fence(source_line)
        if fence is not None:
            continue
        if _TEXT_ALIGNMENT_OPEN.fullmatch(source_line):
            depth += 1
        elif _TEXT_ALIGNMENT_CLOSE.fullmatch(source_line):
            depth -= 1
            if depth == 0:
                return index
    return None


def _opens_code_fence(line: str) -> tuple[str, int] | None:
    match = _CODE_FENCE_OPEN.match(line)
    if match is None:
        return None
    marker = match.group(1)
    return marker[0], len(marker)


def _closes_code_fence(line: str, fence: tuple[str, int]) -> bool:
    match = _CODE_FENCE_CLOSE.fullmatch(line)
    return (
        match is not None
        and match.group(1)[0] == fence[0]
        and len(match.group(1)) >= fence[1]
    )
