import csv
import json
from pathlib import Path
import tempfile
import unittest

from check_archive import check
from recover_archive import CSV_FIELDS


class ArchiveChecks(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.archive, self.csv_path, self.baseline = root / "archive.json", root / "archive.csv", root / "baseline.json"
        self.posts = [dict(id="200", created_at="2026-11-01T03:00:00.500Z", content="new", url="u", media=[]),
                      dict(id="100", created_at="2026-11-01T03:00:00Z", content="old", url="v", media=[])]
        self.baseline.write_text(json.dumps(self.posts[1:]))
        self.write()

    def write(self):
        self.archive.write_text(json.dumps(self.posts))
        with self.csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for post in self.posts:
                writer.writerow({**post, "media": "; ".join(post["media"])})

    def test_allows_unknown_metrics_and_checks_mixed_timestamp_precision(self):
        _, result = check(self.archive, self.csv_path, self.baseline)
        self.assertEqual(result["unique_posts"], 2)
        self.assertEqual(result["additional_ids_since_recovery"], 1)

    def test_rejects_lost_recovered_posts(self):
        self.posts = self.posts[:1]
        self.write()
        with self.assertRaisesRegex(ValueError, "lost 1 recovered"):
            check(self.archive, self.csv_path, self.baseline)

    def test_rejects_duplicate_ids(self):
        self.posts.append(self.posts[-1].copy())
        self.write()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            check(self.archive, self.csv_path, self.baseline)

    def test_rejects_csv_content_mismatch(self):
        self.csv_path.write_text(self.csv_path.read_text().replace(",new,", ",wrong,"))
        with self.assertRaisesRegex(ValueError, "CSV and JSON differ"):
            check(self.archive, self.csv_path, self.baseline)


if __name__ == "__main__":
    unittest.main()
