import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from instascript.source import _download_url


class SourceTests(unittest.TestCase):
    def test_titles_with_delimiters_newlines_and_unicode_are_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            media = Path(root) / "input.webm"
            media.write_bytes(b"fixture")
            metadata = {
                "filepath": str(media),
                "id": "id",
                "title": "Study | notes",
                "description": "First line\nZweite Zeile — étude",
            }
            with patch(
                "instascript.source._run_ytdlp",
                return_value=(0, json.dumps(metadata), ""),
            ):
                result = _download_url("https://example.test/v", Path(root), "")
            self.assertEqual(result["title"], metadata["title"])
            self.assertEqual(result["description"], metadata["description"])

    def test_missing_download_is_not_a_successful_source(self):
        with tempfile.TemporaryDirectory() as root:
            with patch("instascript.source._run_ytdlp", return_value=(0, "{}", "")):
                with self.assertRaises(RuntimeError):
                    _download_url("https://example.test/v", Path(root), "")
