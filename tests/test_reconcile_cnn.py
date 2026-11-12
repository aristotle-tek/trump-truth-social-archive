import csv
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reconcile_cnn import reconcile
from recover_archive import CSV_FIELDS


def post(number, text):
    return dict(id=str(number),created_at='2026-01-01T00:00:00Z',content=text,
                url=f'https://truthsocial.com/@realDonaldTrump/{number}',media=[])


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        previous=Path.cwd();os.chdir(temp.name);self.addCleanup(os.chdir,previous)
        Path('data/cumulative').mkdir(parents=True)
        self.folder=Path('evidence');(self.folder/'feeds').mkdir(parents=True)
        self.old=post(100,'same text')
        for path in ('data/truth_archive.json','data/cumulative/truth_archive.json'):
            Path(path).write_text(json.dumps([self.old]))
        self.patch=patch('reconcile_cnn.subprocess.check_output',return_value='test-revision\n')
        self.patch.start();self.addCleanup(self.patch.stop)

    def test_adds_distinct_id_with_same_text_and_preserves_existing_fields(self):
        changed={**self.old,'content':'different source text'}
        (self.folder/'cnn_snapshot.json').write_text(json.dumps([changed,post(200,'same text')]))
        report=reconcile(self.folder,True)
        records={p['id']:p for p in json.loads(Path('data/truth_archive.json').read_text())}
        self.assertEqual(records['100'],self.old)
        self.assertIn('200',records)
        self.assertEqual(report['after_validation']['unique_posts'],2)
        self.assertEqual(len((self.folder/'imported_records.jsonl').read_text().splitlines()),1)

    def test_duplicate_source_ids_abort_without_modifying_archive(self):
        (self.folder/'cnn_snapshot.json').write_text(json.dumps([post(200,'a'),post(200,'b')]))
        before=Path('data/truth_archive.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'Duplicate source IDs'):
            reconcile(self.folder,True)
        self.assertEqual(Path('data/truth_archive.json').read_bytes(),before)


if __name__=='__main__':
    unittest.main()
