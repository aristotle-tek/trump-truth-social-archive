"""Validate the active archive and optionally report daily post/commit coverage."""

import argparse
from collections import Counter
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import urlparse


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp has no timezone: " + value)
    return parsed.astimezone(timezone.utc)


def check(archive, csv_path, recovery):
    posts = json.loads(Path(archive).read_text())
    if not isinstance(posts, list) or not posts:
        raise ValueError("Archive must be a nonempty JSON array")
    by_id = {}
    dates = []
    for post in posts:
        post_id = post.get("id")
        if not isinstance(post_id, str) or not post_id.isdigit() or post_id in by_id:
            raise ValueError("Invalid or duplicate post ID: " + str(post_id))
        dates.append(timestamp(post["created_at"]))
        if not isinstance(post.get("content"), str) or not isinstance(post.get("media"), list):
            raise ValueError("Invalid content/media for post " + post_id)
        by_id[post_id] = post
    if dates != sorted(dates, reverse=True):
        raise ValueError("Posts must be sorted newest first")
    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        expected_fields = {"id", "created_at", "content", "url", "media",
                           "replies_count", "reblogs_count", "favourites_count"}
        if set(reader.fieldnames or []) != expected_fields:
            raise ValueError("Unexpected CSV columns")
        rows = list(reader)
    if len(rows) != len(posts) or {r["id"] for r in rows} != set(by_id):
        raise ValueError("CSV and JSON post IDs differ")
    for row in rows:
        post = by_id[row["id"]]
        for field, actual in row.items():
            expected = "; ".join(post["media"]) if field == "media" else post.get(field, "")
            if actual != ("" if expected is None else str(expected)):
                raise ValueError(f"CSV and JSON differ for post {row['id']}, field {field}")
    baseline = json.loads(Path(recovery).read_text())
    baseline_ids = {str(p["id"]) for p in baseline}
    missing = baseline_ids - set(by_id)
    if missing:
        raise ValueError(f"Archive lost {len(missing)} recovered post IDs")
    return posts, {
        "status": "passed", "unique_posts": len(posts),
        "recovery_snapshot_ids_retained": len(baseline_ids),
        "additional_ids_since_recovery": len(set(by_id) - baseline_ids),
        "newest_post_utc": dates[0].isoformat(),
        "oldest_post_utc": dates[-1].isoformat(),
        "archive_sha256": hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
    }


def commit_counts(repo, revision, path=None):
    args = ["git", "-C", str(repo), "log", "--first-parent", "--format=%cI", revision]
    if path:
        args.extend(["--", path])
    values = subprocess.check_output(args, text=True).splitlines()
    times = sorted(timestamp(value) for value in values)
    return Counter(value.date().isoformat() for value in times), times


def coverage(posts, validation, repo, revision, output, start, now=None):
    now = now or datetime.now(timezone.utc)
    shallow = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "--is-shallow-repository"], text=True,
    ).strip()
    if shallow != "false":
        raise ValueError("Commit coverage requires full history; fetch --unshallow first")
    revision = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "--verify", revision + "^{commit}"], text=True,
    ).strip()
    all_commits, _ = commit_counts(repo, revision)
    archive_commits, commit_times = commit_counts(repo, revision, "data/truth_archive.json")
    daily_posts = Counter(timestamp(p["created_at"]).date().isoformat() for p in posts)
    accounts = Counter()
    unknown_metrics = 0
    for post in posts:
        parts = urlparse(post.get("url", "")).path.split("/")
        account = parts[1].lower() if len(parts) > 1 and parts[1].startswith("@") else "unknown"
        accounts[account] += 1
        unknown_metrics += any(field not in post for field in ("replies_count", "reblogs_count", "favourites_count"))
    rows, no_posts, no_commits, neither = [], [], [], []
    day = date.fromisoformat(start)
    today = now.astimezone(timezone.utc).date()
    while day <= today:
        key = day.isoformat()
        partial = day == today
        rows.append(dict(date_utc=key, archived_posts=daily_posts[key],
                         archive_commits=archive_commits[key], all_commits=all_commits[key],
                         partial_day=str(partial).lower()))
        if not partial:
            if not daily_posts[key]:
                no_posts.append(key)
            if not archive_commits[key]:
                no_commits.append(key)
            if not daily_posts[key] and not archive_commits[key]:
                neither.append(key)
        day += timedelta(days=1)
    gaps = [dict(start_utc=left.isoformat(), end_utc=right.isoformat(),
                 hours=round((right - left).total_seconds() / 3600, 2))
            for left, right in zip(commit_times, commit_times[1:])
            if left.date().isoformat() >= start and (right - left).total_seconds() > 12 * 3600]
    report = {
        "checked_at_utc": now.isoformat(), "archive_validation": validation,
        "commit_history_revision": revision, "coverage_start_utc": start,
        "coverage_end_utc": today.isoformat(), "final_day_is_partial": True,
        "complete_days_without_posts": no_posts,
        "complete_days_without_archive_commits": no_commits,
        "complete_days_without_posts_or_archive_commits": neither,
        "longest_archive_commit_gaps_over_12_hours": sorted(gaps, key=lambda g: g["hours"], reverse=True)[:10],
        "last_archive_commit_utc": commit_times[-1].isoformat(),
        "hours_since_last_archive_commit_at_check": round((now - commit_times[-1]).total_seconds() / 3600, 2),
        "record_quality": {
            "records_with_trump_account_url": accounts["@realdonaldtrump"],
            "records_with_other_account_url": sum(count for account, count in accounts.items() if account not in ("@realdonaldtrump", "unknown")),
            "records_without_recognized_account_url": accounts["unknown"],
            "records_missing_engagement_counts": unknown_metrics,
            "authorship_note": "Other-account URLs may reflect retruths or older source conventions. The flat archived fields do not reliably establish authorship or distinguish every retruth. Counts describe archived IDs, not a verified count of original Trump-authored posts. Unknown engagement counts remain blank in CSV.",
        },
        "interpretation": "Post counts use post creation dates; commit counts use UTC committer dates on the first-parent history. No commit can mean unchanged output, a failed/skipped run, or no run; it is not proof of missing posts. Days with posts can also be incomplete. Today's partial day is excluded from the no-post/no-commit lists. This is a dated audit, not a live status feed.",
    }
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "daily_coverage.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    (output / "coverage_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("data/truth_archive.json"))
    parser.add_argument("--csv", type=Path, default=Path("data/truth_archive.csv"))
    parser.add_argument("--recovery", type=Path, default=Path("data/cumulative/truth_archive.json"))
    parser.add_argument("--coverage-output", type=Path)
    parser.add_argument("--revision", default="origin/main")
    parser.add_argument("--start", default="2025-10-31")
    args = parser.parse_args()
    posts, validation = check(args.archive, args.csv, args.recovery)
    print(json.dumps(validation, indent=2))
    if args.coverage_output:
        report = coverage(posts, validation, Path.cwd(), args.revision, args.coverage_output, args.start)
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
