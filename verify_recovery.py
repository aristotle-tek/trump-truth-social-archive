"""Independently check recovered files against historical CSV IDs and Git records."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess

from recover_archive import ensure_blobs_available, git, read_blob


CSV_PATHS = ("data/truth_archive.csv", "truth_archive.csv", "fill_missing_5days/truth_archive.csv")


def write_daily_coverage(output, records):
    daily = Counter(p["created_at"][:10] for p in records)
    day, last_day = date.fromisoformat(min(daily)), date.fromisoformat(max(daily))
    empty_recent_dates = []
    with (output / "daily_post_counts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("date_utc", "archived_post_count"))
        while day <= last_day:
            count = daily[day.isoformat()]
            writer.writerow((day.isoformat(), count))
            if not count and day >= date(2025, 10, 26):
                empty_recent_dates.append(day.isoformat())
            day += timedelta(days=1)
    return {
        "zero_post_dates_since_2025_10_26": empty_recent_dates,
        "coverage_note": "A date with no archived posts may reflect no posting or missed collection; it is not proof of either. Nonzero counts also do not establish completeness.",
    }


def verify(repo, output, fetch_missing=False, progress=True):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    report = json.loads((output / "recovery_report.json").read_text())
    for name, expected in report["files_sha256"].items():
        if hashlib.sha256((output / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Recovery file checksum mismatch: " + name)
    records = json.loads((output / "truth_archive.json").read_text())
    posts = {p["id"]: p for p in records}
    if len(posts) != len(records) or len(posts) != report["cumulative_unique_posts"]:
        raise ValueError("Duplicate IDs or incorrect post count")
    # The first recovery used ISO strings; retain support for that dated snapshot.
    sort_key = (lambda p: (datetime.fromisoformat(p["created_at"].replace("Z", "+00:00")), p["id"])) if report.get("sort_policy") == "created_at_utc" else (lambda p: (p["created_at"], p["id"]))
    if records != sorted(records, key=sort_key, reverse=True):
        raise ValueError("Dataset is not sorted newest first")
    with (output / "truth_archive.csv").open(newline="", encoding="utf-8") as handle:
        csv_records = list(csv.DictReader(handle))
    if len(csv_records) != len(posts) or {r["id"] for r in csv_records} != set(posts):
        raise ValueError("Output JSON/CSV IDs differ")
    for row in csv_records:
        post = posts[row["id"]]
        for key, actual in row.items():
            expected = "; ".join(post.get("media", [])) if key == "media" else post.get(key, "")
            if actual != ("" if expected is None else str(expected)):
                raise ValueError(f"JSON/CSV field mismatch for {row['id']} {key}")
    provenance = {}
    with (output / "post_provenance.jsonl").open() as handle:
        for line in handle:
            source = json.loads(line)
            post_id = source["id"]
            if post_id in provenance:
                raise ValueError("Duplicate provenance ID: " + post_id)
            digest = hashlib.sha256(json.dumps(
                posts[post_id], sort_keys=True, ensure_ascii=False, separators=(",", ":"),
            ).encode()).hexdigest()
            if source["record_sha256"] != digest:
                raise ValueError("Provenance record checksum mismatch: " + post_id)
            provenance[post_id] = source
    if set(provenance) != set(posts):
        raise ValueError("Provenance does not cover the dataset")
    history = git(repo, "log", "--full-history", "-m", "--format=", "--raw",
                  "--no-renames", "--no-abbrev", "--root", report["revision"], "--", *CSV_PATHS)
    blobs = sorted({line.split("\t")[0].split()[3] for line in history.splitlines()
                    if line.startswith(":") and line.split("\t")[0].split()[3] != "0" * 40})
    if fetch_missing and blobs:
        subprocess.run(
            ["git", "-C", str(repo), "fetch", "--no-tags", "--no-write-fetch-head", "origin", "--stdin"],
            input="\n".join(blobs) + "\n", text=True, check=True,
        )
    if blobs:
        ensure_blobs_available(repo, blobs)
    process = subprocess.Popen(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    )
    historical_ids, rows_read, sample_count = set(), 0, 0
    try:
        for index, blob in enumerate(blobs):
            payload = read_blob(process, blob)
            reader = csv.reader(io.StringIO(payload.decode("utf-8-sig"), newline=""), strict=True)
            header = next(reader)
            column = header.index("id")
            for row in reader:
                if not row:
                    continue
                post_id = row[column]
                if not post_id.isdigit():
                    raise ValueError(f"Invalid historical CSV ID {post_id!r} in {blob}")
                historical_ids.add(post_id)
                rows_read += 1
            if progress and ((index + 1) % 200 == 0 or index + 1 == len(blobs)):
                print(f"Audited {index + 1}/{len(blobs)} CSV versions; "
                      f"{len(historical_ids):,} distinct IDs", flush=True)
        missing = historical_ids - set(posts)
        if missing:
            raise ValueError(f"Historical CSVs contain {len(missing)} unrecovered IDs: {sorted(missing)[:20]}")
        # Check the first and last recovered post in every month directly in Git.
        months = defaultdict(list)
        for post in records:
            months[post["created_at"][:7]].append(post["id"])
        samples = {post_id for ids in months.values() for post_id in (ids[0], ids[-1])}
        by_blob = defaultdict(list)
        for post_id in samples:
            by_blob[provenance[post_id]["selected_snapshot"]["blob"]].append(post_id)
        for blob, ids in by_blob.items():
            payload = read_blob(process, blob)
            path = provenance[ids[0]]["selected_snapshot"]["path"]
            source_records = ([json.loads(line) for line in payload.splitlines() if line.strip()]
                              if path.endswith(".jsonl") else json.loads(payload))
            source_records = {str(p["id"]): {**p, "id": str(p["id"])} for p in source_records}
            for post_id in ids:
                if posts[post_id] != source_records[post_id]:
                    raise ValueError("Selected record differs from its Git source: " + post_id)
                sample_count += 1
    finally:
        process.stdin.close()
        process.stdout.close()
        code = process.wait()
    if code:
        raise RuntimeError(f"git cat-file exited with {code}")
    coverage = write_daily_coverage(output, records)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "revision": report["revision"], "status": "passed",
        "json_csv_matching_posts": len(posts),
        "post_provenance_checksums_verified": len(provenance),
        "historical_csv_unique_blobs_audited": len(blobs),
        "historical_csv_rows_read": rows_read,
        "historical_csv_unique_ids": len(historical_ids),
        "historical_csv_ids_missing_from_recovery": 0,
        "recovered_ids_not_in_historical_csvs": len(set(posts) - historical_ids),
        "selected_records_checked_against_git": sample_count,
        "record_sample_policy": "First and last recovered post in each calendar month.",
        **coverage,
        "historical_csv_ids_sha256": hashlib.sha256(
            ("\n".join(sorted(historical_ids)) + "\n").encode(),
        ).hexdigest(),
    }
    (output / "validation_report.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).parent)
    parser.add_argument("--output", type=Path, default=Path("data/cumulative"))
    parser.add_argument("--fetch-missing", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(args.repo, args.output, args.fetch_missing), indent=2))


if __name__ == "__main__":
    main()
