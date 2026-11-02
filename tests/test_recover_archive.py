import csv
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from recover_archive import CSV_FIELDS, recover
from verify_recovery import verify


def post(post_id, content):
    return dict(id=post_id, created_at="2025-11-01T12:00:00.000Z",
                content=content, url="https://example.test/" + str(post_id),
                media=[], replies_count=0, reblogs_count=0, favourites_count=0)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Recovery test")
        self.git("config", "user.email", "test@example.test")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True).strip()

    def commit(self, records, extra=None):
        path = self.repo / "data/truth_archive.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(records))
        self.write_csv(self.repo / "data/truth_archive.csv", records)
        if extra:
            path = self.repo / "backfill_2025-10-26_2025-10-30.jsonl"
            path.write_text("\n".join(json.dumps(p) for p in extra) + "\n")
            self.write_csv(self.repo / "truth_archive.csv", extra)
        self.git("add", ".")
        self.git("commit", "-qm", "snapshot")
        return self.git("rev-parse", "HEAD")

    def write_csv(self, path, records):
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for record in records:
                writer.writerow({**record, "media": "; ".join(record["media"])})

    def test_recovers_disappearing_posts_deleted_backfill_and_latest_record(self):
        first_commit = self.commit([post(100, "first"), post("200", "later lost")])
        backfill_commit = self.commit([post("100", "edited")], [post("300", "backfill")])
        (self.repo / "backfill_2025-10-26_2025-10-30.jsonl").unlink()
        last_commit = self.commit([post("100", "edited"), post("400", "new")])
        output = self.repo / "recovered"
        report = recover(self.repo, "HEAD", output, progress=False)
        result = {p["id"]: p for p in json.loads((output / "truth_archive.json").read_text())}
        self.assertEqual(set(result), {"100", "200", "300", "400"})
        self.assertEqual(result["100"]["content"], "edited")
        self.assertEqual(report["additional_posts_recovered"], 2)
        provenance = {p["id"]: p for p in map(json.loads, (output / "post_provenance.jsonl").read_text().splitlines())}
        self.assertEqual(provenance["200"]["first_snapshot"]["commit"], first_commit)
        self.assertEqual(provenance["300"]["selected_snapshot"]["commit"], backfill_commit)
        self.assertEqual(provenance["100"]["selected_snapshot"]["commit"], last_commit)
        for name, digest in report["files_sha256"].items():
            self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
        validation = verify(self.repo, output, progress=False)
        self.assertEqual(validation["historical_csv_unique_ids"], 4)
        self.assertEqual(validation["status"], "passed")
        with self.assertRaisesRegex(ValueError, "already exists"):
            recover(self.repo, "HEAD", output, progress=False)

    def test_invalid_historical_snapshot_aborts_without_publishing(self):
        self.commit([post("100", "valid")])
        invalid = post("bad-id", "invalid")
        self.commit([invalid])
        self.commit([post("200", "valid again")])
        output = self.repo / "recovered"
        with self.assertRaisesRegex(ValueError, "Invalid post ID"):
            recover(self.repo, "HEAD", output, progress=False)
        self.assertFalse(output.exists())

    def test_csv_audit_detects_a_post_missing_from_json_history(self):
        self.commit([post("100", "JSON")])
        self.write_csv(self.repo / "truth_archive.csv", [post("500", "CSV only")])
        self.git("add", ".")
        self.git("commit", "-qm", "CSV-only post")
        output = self.repo / "recovered"
        recover(self.repo, "HEAD", output, progress=False)
        with self.assertRaisesRegex(ValueError, "1 unrecovered IDs"):
            verify(self.repo, output, progress=False)


if __name__ == "__main__":
    unittest.main()
