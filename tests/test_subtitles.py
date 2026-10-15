import json
import tempfile
import unittest
from pathlib import Path

from instascript.subtitles import export_item, render, timestamp


class SubtitleTests(unittest.TestCase):
    def setUp(self):
        self.transcript = {
            "segments": [
                {"start": 0, "end": 2.5, "text": "أهلاً بالعالم"},
                {"start": 60.001, "end": 62, "text": "Second line"},
            ]
        }

    def test_srt_uses_numbered_cues_and_comma_milliseconds(self):
        self.assertEqual(
            render(self.transcript, "srt"),
            "1\n00:00:00,000 --> 00:00:02,500\nأهلاً بالعالم\n\n2\n00:01:00,001 --> 00:01:02,000\nSecond line\n",
        )

    def test_webvtt_header_and_dot_milliseconds(self):
        self.assertTrue(
            render(self.transcript, "vtt").startswith("WEBVTT\n\n1\n00:00:00.000")
        )

    def test_timestamp_rounding_carries_into_minutes_and_hours(self):
        self.assertEqual(timestamp(59.9996), "00:01:00,000")
        self.assertEqual(timestamp(3599.9996), "01:00:00,000")

    def test_invalid_times_and_reversed_ranges(self):
        for bad in [-1, float("nan"), float("inf"), "1", None, True]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                timestamp(bad)
        with self.assertRaises(ValueError):
            render({"segments": [{"start": 2, "end": 1, "text": "text"}]}, "srt")

    def test_blank_segments_are_omitted_and_cues_are_contiguous(self):
        transcript = {
            "segments": [
                {"start": 0, "end": 1, "text": "  "},
                {"start": 1, "end": 2, "text": "one\n\n two"},
            ]
        }
        self.assertEqual(
            render(transcript, "srt"), "1\n00:00:01,000 --> 00:00:02,000\none\ntwo\n"
        )

    def test_empty_transcript_and_invalid_structure(self):
        self.assertEqual(render({"segments": []}, "srt"), "")
        self.assertEqual(render({"segments": []}, "vtt"), "WEBVTT\n\n")
        for bad in [{}, {"segments": None}, {"segments": [None]}]:
            with self.assertRaises(ValueError):
                render(bad, "srt")
        with self.assertRaises(ValueError):
            render(self.transcript, "html")

    def test_export_preserves_canonical_json(self):
        with tempfile.TemporaryDirectory() as directory:
            item = Path(directory)
            canonical = json.dumps(self.transcript, ensure_ascii=False)
            (item / "transcript.json").write_text(canonical, encoding="utf-8")
            output = export_item(item, "srt")
            self.assertIn("أهلاً", output.read_text(encoding="utf-8"))
            self.assertEqual(
                (item / "transcript.json").read_text(encoding="utf-8"), canonical
            )

    def test_missing_file_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            item = Path(directory)
            with self.assertRaises(FileNotFoundError):
                export_item(item, "vtt")
            self.assertFalse((item / "transcript.vtt").exists())


if __name__ == "__main__":
    unittest.main()
