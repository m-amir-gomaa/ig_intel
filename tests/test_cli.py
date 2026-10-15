import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from instascript import cli


class CliTests(unittest.TestCase):
    def test_failed_partial_items_are_not_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.json").write_text(
                json.dumps({"url_sha256": "url", "content_sha256": "audio"})
            )
            self.assertEqual(cli._existing_index([root]), ({}, {}))
            (root / "transcript.json").write_text('{"duration":1,"segments":[]}')
            self.assertEqual(cli._existing_index([root]), ({}, {}))
            (root / "complete.json").write_text(
                json.dumps(
                    {
                        "files": {
                            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in root.iterdir()
                            if p.is_file()
                        }
                    }
                )
            )
            urls, content = cli._existing_index([root, root])
            self.assertEqual(urls, {"url": str(root)})
            self.assertEqual(content, {"audio": str(root)})

    @patch.object(cli.ui, "error")
    def test_pipeline_failure_returns_error_without_stopping_caller(self, error):
        with patch.object(
            cli, "_run_single", side_effect=RuntimeError("download unavailable")
        ):
            self.assertEqual(
                cli.run_single("https://example.test/video", argparse.Namespace()),
                (1, "error"),
            )
        error.assert_called_once()

    def test_queue_keeps_failures_and_comments_and_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "queue.md"
            queue.write_text(
                "# My queue\n- [ ] failed\n- [ ] good\n- [ ] duplicate\n- [x] history\n"
            )
            with (
                patch.object(
                    cli,
                    "run_single",
                    side_effect=[(1, "error"), (0, "done"), (0, "dup")],
                ) as run,
                patch.object(cli.ui, "banner"),
                patch.object(cli.ui, "summary"),
            ):
                self.assertEqual(cli.run_queue(argparse.Namespace(queue=str(queue))), 1)
            self.assertEqual(run.call_count, 3)
            self.assertEqual(
                queue.read_text(), "# My queue\n- [ ] failed\n- [x] history\n"
            )


if __name__ == "__main__":
    unittest.main()
