import json
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests
import scrape


def archived(post_id):
    return dict(id=str(post_id), created_at="2026-10-31T12:00:00.000Z",
                content="saved text", url="https://example.test/" + str(post_id),
                media=[], replies_count=1, reblogs_count=2, favourites_count=3)


def raw(post_id):
    record = archived(post_id)
    record["media_attachments"] = []
    return record


class CumulativeScrapeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.json_path, self.csv_path = root / "cumulative.json", root / "cumulative.csv"
        self.legacy = root / "legacy.json"
        self.original = [archived(i) for i in (250, 100, 50)]
        self.json_path.write_text(json.dumps(self.original))
        self.csv_path.write_text("original CSV\n")
        self.legacy.write_text(json.dumps([archived(999)]))
        for name, value in (("OUTPUT_JSON_FILE", self.json_path),
                            ("OUTPUT_CSV_FILE", self.csv_path),
                            ("RECOVERY_JSON_FILE", self.legacy)):
            patcher = patch.object(scrape, name, str(value))
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(scrape.requests, "get", side_effect=AssertionError("Unexpected bootstrap request"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_retains_cumulative_posts_and_deduplicates_overlapping_pages(self):
        pages = [[raw(300), raw(250)], [raw(200), raw(200), raw(100)], [raw(50)]]
        with patch.object(scrape, "scrape", side_effect=pages) as request:
            scrape.fetch_posts()
        result = json.loads(self.json_path.read_text())
        self.assertEqual({p["id"] for p in result}, {"300", "250", "200", "100", "50"})
        self.assertEqual(len(result), 5)
        self.assertIn("max_id=250", request.call_args_list[1].args[0])
        self.assertIn("max_id=100", request.call_args_list[2].args[0])
        self.assertEqual(json.loads(self.legacy.read_text()), [archived(999)])

    def test_network_failure_after_a_page_preserves_both_outputs(self):
        before = self.json_path.read_bytes(), self.csv_path.read_bytes()
        with patch.object(scrape, "scrape", side_effect=[[raw(300)], requests.ConnectionError("failed")]):
            with self.assertRaises(requests.ConnectionError):
                scrape.fetch_posts()
        self.assertEqual(before, (self.json_path.read_bytes(), self.csv_path.read_bytes()))

    def test_corrupt_cumulative_archive_does_not_fall_back_to_older_data(self):
        self.json_path.write_text("broken JSON")
        with self.assertRaises(json.JSONDecodeError):
            scrape.load_existing_posts()
        self.assertEqual(self.json_path.read_text(), "broken JSON")

    def test_empty_page_stops_and_retains_existing_posts(self):
        with patch.object(scrape, "scrape", return_value=[]) as request:
            scrape.fetch_posts()
        self.assertEqual(request.call_count, 1)
        self.assertEqual({p["id"] for p in json.loads(self.json_path.read_text())}, {"250", "100", "50"})

    def test_page_limit_fails_instead_of_silently_skipping_a_backlog(self):
        before = self.json_path.read_bytes()
        with patch.object(scrape, "scrape", return_value=[raw(300)]):
            with self.assertRaisesRegex(RuntimeError, "increase max_pages"):
                scrape.fetch_posts(max_pages=1)
        self.assertEqual(before, self.json_path.read_bytes())

    def test_missing_archives_fail_instead_of_restarting_from_upstream(self):
        self.json_path.unlink()
        self.legacy.unlink()
        with self.assertRaises(FileNotFoundError):
            scrape.load_existing_posts()

    def test_new_posts_keep_unicode_and_decode_html_entities(self):
        record = raw(300)
        record["content"] = '<p>“Café” &amp; 🇺🇸</p>'
        result = scrape.extract_posts([record], {})
        self.assertEqual(result[0]["content"], '“Café” & 🇺🇸')

    def test_absent_historical_metrics_remain_blank_in_csv(self):
        self.original[0].pop("favourites_count")
        self.json_path.write_text(json.dumps(self.original))
        with patch.object(scrape, "scrape", return_value=[]):
            scrape.fetch_posts()
        with self.csv_path.open(newline="") as handle:
            rows = {r["id"]: r for r in csv.DictReader(handle)}
        self.assertEqual(rows["250"]["favourites_count"], "")

    def test_fetch_sorts_mixed_precision_timestamps_by_actual_time(self):
        self.original[0]["created_at"] = "2026-10-31T12:00:00Z"
        self.json_path.write_text(json.dumps(self.original))
        new = raw(300)
        new["created_at"] = "2026-10-31T12:00:00.500Z"
        with patch.object(scrape, "scrape", side_effect=[[new], [raw(100)]]):
            scrape.fetch_posts()
        self.assertEqual(json.loads(self.json_path.read_text())[0]["id"], "300")


if __name__ == "__main__":
    unittest.main()
