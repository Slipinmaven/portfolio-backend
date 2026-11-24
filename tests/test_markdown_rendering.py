import unittest
from uuid import uuid4

from app.application.posts.markdown import (
    inline_media_image_references,
    inline_media_references,
    render_markdown,
)


class MarkdownRenderingTests(unittest.TestCase):
    def test_text_alignment_wraps_formatted_markdown(self) -> None:
        html = render_markdown(
            ':::textAlignment {alignment="center"}\n\n'
            "**Centered text**\n\n"
            ":::"
        )

        self.assertIn('<div style="text-align: center;">', html)
        self.assertIn("<p><strong>Centered text</strong></p>", html)
        self.assertIn("</div>", html)

    def test_text_alignment_does_not_match_markers_inside_code_fences(self) -> None:
        html = render_markdown(
            '```markdown\n'
            ':::textAlignment {alignment="center"}\n'
            "Centered text\n"
            ":::\n"
            "```"
        )

        self.assertNotIn('<div style="text-align: center;">', html)
        self.assertIn("textAlignment", html)

    def test_text_alignment_resolves_inline_media_inside_aligned_content(self) -> None:
        media_id = uuid4()
        html = render_markdown(
            f':::textAlignment {{alignment="right"}}\n\n'
            f"![Diagram](media:{media_id})\n\n"
            ":::",
            media_url_resolver=lambda requested_id: (
                f"/api/v1/media/{requested_id}/content"
            ),
        )

        self.assertIn('<div style="text-align: right;">', html)
        self.assertIn(f'src="/api/v1/media/{media_id}/content"', html)

    def test_inline_media_references_distinguish_video_and_document(self) -> None:
        image_id = uuid4()
        video_id = uuid4()
        document_id = uuid4()
        body = (
            f"![Diagram](media:{image_id})\n\n"
            f'![Walkthrough](media:{video_id} "media-video")\n\n'
            f"[Download report](media:{document_id})\n\n"
            f'```markdown\n![Not a reference](media:{uuid4()})\n```'
        )

        self.assertEqual(
            inline_media_references(body),
            [
                ("IMAGE", "Diagram", image_id),
                ("VIDEO", "Walkthrough", video_id),
                ("DOCUMENT", "Download report", document_id),
            ],
        )
        self.assertEqual(
            inline_media_image_references(body),
            [("Diagram", image_id)],
        )

    def test_video_and_document_references_render_with_separate_resolvers(self) -> None:
        video_id = uuid4()
        document_id = uuid4()
        html = render_markdown(
            f'![A "walkthrough"](media:{video_id} "media-video")\n\n'
            f"[Download the report](media:{document_id})",
            media_video_url_resolver=lambda requested_id: (
                f"/api/v1/media/{requested_id}/content"
            ),
            media_download_url_resolver=lambda requested_id: (
                f"/api/v1/media/{requested_id}/content"
            ),
        )

        self.assertIn(
            f'aria-label="A &quot;walkthrough&quot;" '
            f'src="/api/v1/media/{video_id}/content"',
            html,
        )
        self.assertIn(
            f'<a href="/api/v1/media/{document_id}/content" download="">'
            "Download the report</a>",
            html,
        )

    def test_unresolved_video_and_document_references_do_not_expose_raw_tokens(self) -> None:
        video_id = uuid4()
        document_id = uuid4()
        html = render_markdown(
            f'![Walkthrough](media:{video_id} "media-video")\n\n'
            f"[Download report](media:{document_id})"
        )

        self.assertIn("Video unavailable", html)
        self.assertIn('aria-disabled="true"', html)
        self.assertNotIn(f"media:{document_id}", html)
