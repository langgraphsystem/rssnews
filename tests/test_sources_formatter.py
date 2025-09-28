import unittest

from bot_service.formatters import MessageFormatter


class TestSourcesFormatter(unittest.TestCase):
    def test_render_sources_block_html_escaping(self):
        fmt = MessageFormatter()
        sources = [
            {
                "title": "Policy & oversight <update>",
                "url": "https://www.ice.gov/news/123?x=1&y=2",
                "source_name": "ice.gov",
                "published_at": "2025-09-27T11:22:33Z",
            },
            {
                "title": "Reuters: \"report\" & analysis",
                "url": "https://www.reuters.com/world/us/xyz",
                "source_name": "reuters.com",
                "published_at": "2025-09-26",
            },
        ]

        html_block = fmt.render_sources_block(sources)

        self.assertIn("📚 <b>Sources</b>", html_block)
        # Check escaping of &, <, > and quotes
        self.assertIn(
            '<a href="https://www.ice.gov/news/123?x=1&amp;y=2">',
            html_block,
        )
        self.assertIn(
            "Policy &amp; oversight &lt;update&gt; — ice.gov",
            html_block,
        )
        self.assertIn(
            "Reuters: &quot;report&quot; &amp; analysis — reuters.com",
            html_block,
        )
        # Dates rendered as YYYY-MM-DD
        self.assertIn("· 2025-09-27", html_block)
        self.assertIn("· 2025-09-26", html_block)


if __name__ == "__main__":
    unittest.main()

