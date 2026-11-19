"""Decide when collection is due and record successful validated collections."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

from check_archive import check, timestamp

STATUS = Path('data/collection_status.json')


def collection_due(status, event, now=None):
    now = now or datetime.now(timezone.utc)
    if event != 'schedule':
        return True, 'Manual or external trigger requests collection'
    try:
        completed = timestamp(status['last_successful_collection_at_utc'])
    except (KeyError, TypeError, ValueError):
        return True, 'No valid collection heartbeat; collect now'
    age = now - completed
    if age < timedelta(0):
        return True, 'Heartbeat is in the future; collect now'
    return age >= timedelta(hours=3), f'Last successful collection was {age.total_seconds()/3600:.2f} hours ago'


def read_status(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def record_success(path=STATUS):
    _, validation = check('data/truth_archive.json', 'data/truth_archive.csv', 'data/cumulative/truth_archive.json')
    report = {
        'schema_version': 1,
        'last_successful_collection_at_utc': datetime.now(timezone.utc).isoformat(),
        'workflow_run_url': f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'aristotle-tek/trump-truth-social-archive')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}",
        'archive_validation': validation,
        'meaning': 'A live fetch completed and the archive passed validation. The heartbeat is published with the archive; post creation time is not collection time.',
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2)+'\n')
    temporary.replace(path)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('due', 'record-success'))
    args = parser.parse_args()
    if args.action == 'record-success':
        print(json.dumps(record_success(), indent=2))
    else:
        due, reason = collection_due(read_status(STATUS), os.environ.get('GITHUB_EVENT_NAME', 'manual'))
        print(reason)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as handle:
                handle.write(f'collect={str(due).lower()}\n')
        print(f'Collection due: {due}')
