import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from instascript.pipeline import ingest, complete_item
from instascript.contract import bundle, validate_review


def transcript():
    return {
        "model": "fixture",
        "language": "en",
        "duration": 2.0,
        "audio_file": "audio.wav",
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 2.0,
                "text": "A testable claim.",
                "words": [],
            }
        ],
    }


class PipelineTests(unittest.TestCase):
    def test_review_requires_exact_quotes_and_existing_segment_ids(self):
        raw = transcript()
        review = {
            "summary_md": "The speaker makes a claim.",
            "corrections": [],
            "claims": [
                {
                    "segment_id": "s000000",
                    "quote": "A testable claim.",
                    "question": "What supports it?",
                }
            ],
        }
        self.assertEqual(
            validate_review(raw, review)["claims"][0]["segment_id"], "s000000"
        )
        review["claims"][0]["quote"] = "An invented claim."
        with self.assertRaises(ValueError):
            validate_review(raw, review)

    def test_bundle_preserves_original_and_separates_derived_text(self):
        raw = transcript()
        original = json.dumps(raw)
        files = bundle(
            raw, {"title": "Fixture", "kind": "local", "input": "fixture.wav"}, None, {}
        )
        self.assertIn("transcript.md", files)
        self.assertIn("instascript-export/v1", files["manifest.json"])
        self.assertEqual(json.dumps(raw), original)

    def test_failed_requested_review_does_not_publish_and_retry_reuses_asr(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            src = root / "source.wav"
            src.write_bytes(b"fixture")

            def normalize(media, output):
                output.write_bytes(b"normalized")
                return output

            with (
                patch("instascript.pipeline.audio.normalize", side_effect=normalize),
                patch("instascript.pipeline.source.hash_audio", return_value="a" * 64),
                patch(
                    "instascript.pipeline.transcribe.transcribe",
                    return_value=transcript(),
                ) as model,
                patch(
                    "instascript.pipeline.review_transcript",
                    side_effect=[
                        RuntimeError("provider unavailable"),
                        {"summary_md": "Summary", "claims": [], "corrections": []},
                    ],
                ),
            ):
                with self.assertRaises(RuntimeError):
                    ingest(str(src), root / "out", review=True)
                self.assertEqual(list((root / "out").glob("*/complete.json")), [])
                result = ingest(str(src), root / "out", review=True)
                self.assertTrue(complete_item(result))
                self.assertEqual(model.call_count, 1)

    def test_different_media_same_filename_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("one", "two"):
                (root / name).mkdir()
                (root / name / "same.wav").write_bytes(name.encode())

            def normalize(media, output):
                output.write_bytes(media.read_bytes())
                return output

            with (
                patch("instascript.pipeline.audio.normalize", side_effect=normalize),
                patch(
                    "instascript.pipeline.source.hash_audio",
                    side_effect=lambda p: (
                        __import__("hashlib").sha256(p.read_bytes()).hexdigest()
                    ),
                ),
                patch(
                    "instascript.pipeline.transcribe.transcribe",
                    return_value=transcript(),
                ),
            ):
                a = ingest(str(root / "one/same.wav"), root / "out")
                b = ingest(str(root / "two/same.wav"), root / "out")
                self.assertNotEqual(a, b)
                self.assertTrue(complete_item(a))
                self.assertTrue(complete_item(b))

    def test_completion_detects_corrupt_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            src = root / "a.wav"
            src.write_bytes(b"fixture")

            def normalize(media, output):
                output.write_bytes(b"fixture")
                return output

            with (
                patch("instascript.pipeline.audio.normalize", side_effect=normalize),
                patch("instascript.pipeline.source.hash_audio", return_value="a" * 64),
                patch(
                    "instascript.pipeline.transcribe.transcribe",
                    return_value=transcript(),
                ),
            ):
                item = ingest(str(src), root / "out")
            (item / "transcript.json").write_text("{broken")
            self.assertFalse(complete_item(item))
