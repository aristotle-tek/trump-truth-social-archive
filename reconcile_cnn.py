"""Reconcile a saved CNN snapshot and public RSS evidence without editing old records.

Run on a clean, synchronized checkout. This is a manual, dated reconciliation;
the scheduled collector does not run it. Missing candidates must have a numeric
ID matching their Trump-account URL and valid archive fields. Repeated text is
reported, not treated as proof that distinct posting IDs are duplicates.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

from check_archive import timestamp, check
from scrape import save_archive

ZERO_DATES = ('2025-11-13', '2025-12-21', '2025-12-29', '2026-06-07')


def text_key(post):
    return re.sub(r'\s+', ' ', post.get('content', '')).strip()


def reconcile(folder, apply=False):
    folder = Path(folder)
    if (folder / 'report.json').exists():
        raise ValueError('Use a new dated folder; completed evidence must not be overwritten')
    active = Path('data/truth_archive.json')
    before_bytes = active.read_bytes()
    before = json.loads(before_bytes)
    cnn_bytes = (folder / 'cnn_snapshot.json').read_bytes()
    cnn = json.loads(cnn_bytes)
    ours = {p['id']: p for p in before}
    theirs = {str(p['id']): p for p in cnn}
    if len(ours) != len(before) or len(theirs) != len(cnn):
        raise ValueError('Duplicate source IDs require manual review')
    evidence = {}
    feed_counts, capped = {}, []
    for path in sorted((folder / 'feeds').glob('*.xml.gz')):
        root = ET.fromstring(gzip.open(path, 'rb').read())
        items = root.findall('./channel/item')
        if len(items) >= 500:
            capped.append(path.name)
        feed_counts[path.name] = len(items)
        for item in items:
            post_id = item.findtext('{https://truthsocial.com/ns}originalId')
            if not post_id:
                continue
            evidence[post_id] = {
                'archive_url': item.findtext('link'),
                'truth_url': item.findtext('{https://truthsocial.com/ns}originalUrl'),
                'created_at_utc': parsedate_to_datetime(item.findtext('pubDate')).astimezone(timezone.utc).isoformat(),
                'post_type': item.findtext('{https://www.trumpstruth.org/rss-extensions}postType'),
                'removed': item.findtext('{https://www.trumpstruth.org/rss-extensions}removed'),
                'evidence_file': str(path),
            }
    missing = [p for p in cnn if str(p['id']) not in ours]
    existing_urls = {p['url'] for p in before}
    for post in missing:
        if not re.fullmatch(r'https://truthsocial\.com/@realDonaldTrump/' + re.escape(str(post['id'])), post.get('url', ''), re.I):
            raise ValueError('Candidate ID/URL mismatch')
        timestamp(post['created_at'])
        if post['url'] in existing_urls or not isinstance(post['media'], list) or not isinstance(post['content'], str):
            raise ValueError('Candidate duplicates a URL or has invalid fields')
    own_only = [p for p in before if p['id'] not in theirs]
    cnn_texts = {text_key(p) for p in cnn if text_key(p)}
    rows = []
    for lane, records in [('ours_only', own_only), ('cnn_only', missing)]:
        for post in records:
            third = evidence.get(post['id'], {})
            delta = abs((timestamp(post['created_at']) - timestamp(third['created_at_utc'])).total_seconds()) if third else None
            rows.append(dict(lane=lane, id=post['id'], url=post['url'], created_at=post['created_at'],
                             trump_account_url='/@realdonaldtrump/' in post['url'].lower(),
                             third_archive_confirmed=bool(third), third_archive_type=third.get('post_type'),
                             third_archive_timestamp_difference_seconds=delta,
                             same_text_in_cnn=text_key(post) in cnn_texts,
                             third_archive_url=third.get('archive_url')))
    with (folder / 'unmatched_ids.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader(); writer.writerows(rows)
    with (folder / 'imported_records.jsonl').open('w', encoding='utf-8') as handle:
        for post in missing:
            handle.write(json.dumps({'record': post, 'source_url': 'https://ix.cnn.io/data/truth-social/truth_archive.json',
                                     'source_snapshot': str(folder / 'cnn_snapshot.json'),
                                     'source_snapshot_sha256': hashlib.sha256(cnn_bytes).hexdigest(),
                                     'third_archive': evidence.get(post['id']),
                                     'record_sha256': hashlib.sha256(json.dumps(post, sort_keys=True).encode()).hexdigest()}) + '\n')
    own_trump = [r for r in rows if r['lane'] == 'ours_only' and r['trump_account_url']]
    third_confirmed = [r for r in own_trump if r['third_archive_confirmed']]
    dates = {}
    for day in ZERO_DATES:
        dates[day] = {
            'existing_records': sum(p['created_at'].startswith(day) for p in before),
            'cnn_records': sum(p['created_at'].startswith(day) for p in cnn),
            'third_archive_utc_records_in_fetched_windows': sum(timestamp(p['created_at_utc']).date().isoformat() == day for p in evidence.values()),
            'surrounding_window_items': feed_counts.get(day + '.xml.gz'),
        }
    report = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  before_git_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                  before_archive_sha256=hashlib.sha256(before_bytes).hexdigest(),
                  cnn_snapshot_sha256=hashlib.sha256(cnn_bytes).hexdigest(),
                  before_count=len(before), cnn_count=len(cnn), shared_ids=len(set(ours)&set(theirs)),
                  cnn_only_ids=len(missing), ours_only_ids=len(own_only),
                  ours_only_trump_url_ids=len(own_trump),
                  ours_only_trump_url_ids_confirmed_by_third_archive=len(third_confirmed),
                  third_confirmed_own_ids_timestamp_disagreements_over_60_seconds=sum((r['third_archive_timestamp_difference_seconds'] or 0)>60 for r in third_confirmed),
                  ours_only_trump_url_ids_with_same_text_in_cnn=sum(r['same_text_in_cnn'] for r in own_trump),
                  cnn_only_ids_confirmed_by_third_archive=sum(p['id'] in evidence for p in missing),
                  third_archive_capped_feeds=capped, zero_dates=dates,
                  interpretation='Exact IDs identify archive records. Repeated text at distinct IDs can be reposting. Third-archive matches corroborate stored identity, not authenticity of every statement or complete platform coverage. Missing posts cannot be inferred from empty dates alone. Existing fields and records are never overwritten.',
                  applied=apply)
    if apply:
        merged = dict(ours)
        merged.update({str(p['id']): p for p in missing})
        assert all(merged[key] == value for key,value in ours.items())
        save_archive(sorted(merged.values(), key=lambda p: timestamp(p['created_at']), reverse=True))
        _, validation = check(active, 'data/truth_archive.csv', 'data/cumulative/truth_archive.json')
        report['after_validation'] = validation
        report['existing_records_preserved_unchanged'] = len(ours)
    (folder / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    print(json.dumps(reconcile(args.folder,args.apply),indent=2))
