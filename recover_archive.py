"""Rebuild a cumulative archive from every JSON snapshot reachable in Git.

This reads complete JSON objects, rather than trying to parse fragments of a
Git diff. Records are deduplicated by post ID; the last committed observation
in Git's topological history wins. Original records stay unchanged apart from
normalizing IDs to strings. Source commits are saved separately.
"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


ARCHIVE_PATHS = (
    "data/truth_archive.json",
    "truth_archive.json",
    "fill_missing_5days/truth_archive.json",
    "backfill_2025-10-25_2025-10-31.jsonl",
    "backfill_2025-10-26_2025-10-30.jsonl",
    "fill_missing_5days/backfill_2025-10-25_2025-10-31.jsonl",
    "fill_missing_5days/backfill_2025-10-26_2025-10-30.jsonl",
)
CSV_FIELDS = (
    "id", "created_at", "content", "url", "media",
    "replies_count", "reblogs_count", "favourites_count",
)


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def inventory(repo, revision):
    if git(repo, "rev-parse", "--is-shallow-repository") != "false":
        raise ValueError("Full history is required. Fetch with --unshallow first.")
    head = git(repo, "rev-parse", "--verify", revision + "^{commit}")
    history = git(
        repo, "log", "--full-history", "-m", "--reverse", "--topo-order",
        "--format=COMMIT\t%H\t%cI", "--raw", "--no-renames",
        "--no-abbrev", "--root", head, "--", *ARCHIVE_PATHS,
    )
    snapshots = []
    seen = set()
    for line in history.splitlines():
        if line.startswith("COMMIT\t"):
            _, commit, committed_at = line.split("\t")
        elif line.startswith(":"):
            metadata, path = line.split("\t")
            blob = metadata.split()[3]
            key = (commit, path, blob)
            if blob != "0" * 40 and key not in seen:
                seen.add(key)
                snapshots.append(dict(
                    commit=commit, committed_at=committed_at, path=path, blob=blob,
                ))
    if not snapshots:
        raise ValueError("No archive snapshots found.")
    return head, snapshots


def validate_posts(payload, source):
    records = (
        [json.loads(line) for line in payload.splitlines() if line.strip()]
        if source["path"].endswith(".jsonl") else json.loads(payload)
    )
    if not isinstance(records, list):
        raise ValueError("Archive is not a JSON array: " + str(source))
    normalized = {}
    for post in records:
        if not isinstance(post, dict) or not str(post.get("id", "")).isdigit():
            raise ValueError("Invalid post ID in " + str(source))
        datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
        if not isinstance(post.get("media", []), list):
            raise ValueError("Invalid media array in " + str(source))
        post["id"] = str(post["id"])
        # A historical file can contain duplicate IDs; its last row wins.
        normalized[post["id"]] = post
    return records, normalized


def read_blob(process, blob):
    process.stdin.write((blob + "\n").encode())
    process.stdin.flush()
    header = process.stdout.readline().decode().strip().split()
    if len(header) != 3 or header[1] != "blob":
        raise ValueError(f"Cannot read Git blob {blob}: {header}. Use --fetch-missing.")
    size = int(header[2])
    payload = process.stdout.read(size)
    if len(payload) != size or process.stdout.read(1) != b"\n":
        raise ValueError("Incomplete Git blob: " + blob)
    return payload


def ensure_blobs_available(repo, blobs):
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch-check=%(objectname) %(objecttype)"],
        input="\n".join(blobs) + "\n", text=True, capture_output=True, check=True,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    )
    missing = [line for line in result.stdout.splitlines() if not line.endswith(" blob")]
    if missing:
        raise ValueError(f"{len(missing)} historical blobs are unavailable: {missing[:3]}. Use --fetch-missing.")


def recover(repo, revision, output, fetch_missing=False, progress=True):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("Output already exists; choose a new directory: " + str(output))
    head, snapshots = inventory(repo, revision)
    blobs = sorted({s["blob"] for s in snapshots})
    if fetch_missing:
        subprocess.run(
            ["git", "-C", str(repo), "fetch", "--no-tags", "--no-write-fetch-head",
             "origin", "--stdin"],
            input="\n".join(blobs) + "\n", text=True, check=True,
        )
    ensure_blobs_available(repo, blobs)
    posts, provenance, summaries = {}, {}, []
    baseline_ids = set()
    # Do not silently launch network requests while auditing local objects.
    process = subprocess.Popen(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    )
    rows_read = 0
    try:
        for index, snapshot in enumerate(snapshots):
            payload = read_blob(process, snapshot["blob"])
            records, normalized = validate_posts(payload, snapshot)
            added, changed = 0, 0
            for post_id, post in normalized.items():
                if post_id not in posts:
                    added += 1
                    provenance[post_id] = [index, index, 1, 0]
                else:
                    info = provenance[post_id]
                    info[1] = index
                    info[2] += 1
                    if posts[post_id] != post:
                        info[3] += 1
                        changed += 1
                posts[post_id] = post
            rows_read += len(records)
            summaries.append({**snapshot, "rows": len(records),
                              "unique_ids": len(normalized), "new_ids": added,
                              "changed_records": changed,
                              "duplicate_rows": len(records) - len(normalized)})
            if progress and ((index + 1) % 100 == 0 or index + 1 == len(snapshots)):
                print(f"Read {index + 1}/{len(snapshots)} snapshots; "
                      f"{len(posts):,} unique posts", flush=True)
        # Compare with the existing main archive at the requested revision.
        for path in ("data/truth_archive.json", "truth_archive.json"):
            object_name = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "--verify", f"{head}:{path}"],
                text=True, capture_output=True,
            )
            if object_name.returncode == 0:
                _, current = validate_posts(
                    read_blob(process, object_name.stdout.strip()), {"path": path},
                )
                baseline_ids = set(current)
                break
    finally:
        process.stdin.close()
        process.stdout.close()
        code = process.wait()
    if code:
        raise RuntimeError(f"git cat-file exited with {code}")
    if not posts or not baseline_ids.issubset(posts):
        raise ValueError("Recovery failed to retain every post from the current archive.")
    ordered = sorted(posts.values(), key=lambda p: (datetime.fromisoformat(p["created_at"].replace("Z", "+00:00")), p["id"]), reverse=True)
    months = Counter(p["created_at"][:7] for p in ordered)
    generated_at = datetime.now(timezone.utc).isoformat()
    report = {
        "generated_at": generated_at,
        "revision": head,
        "reachable_commits": int(git(repo, "rev-list", "--count", head)),
        "archive_paths": list(ARCHIVE_PATHS),
        "snapshots_processed": len(snapshots),
        "unique_blobs_processed": len(blobs),
        "source_rows_read": rows_read,
        "source_duplicate_rows": sum(s["duplicate_rows"] for s in summaries),
        "current_archive_unique_posts": len(baseline_ids),
        "cumulative_unique_posts": len(posts),
        "additional_posts_recovered": len(set(posts) - baseline_ids),
        "oldest_post": ordered[-1]["created_at"],
        "newest_post": ordered[0]["created_at"],
        "posts_by_month": dict(sorted(months.items())),
        "selection_policy": "Last observation in oldest-to-newest topological Git order; IDs normalized to strings; other fields retained as stored.",
        "sort_policy": "created_at_utc",
        "completeness": "Union of all post IDs in the listed JSON/JSONL paths reachable from revision. This does not establish completeness against Truth Social or recover posts never committed. Historical CSV files were not used as independent sources.",
        "provenance_note": "First/last refer to inspected file-change snapshots, not to continuous presence or the actual scraping time. Engagement counts are archived observations, not current totals. Content and encoding are retained as stored.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".archive-recovery-", dir=output.parent) as temp:
        temp = Path(temp)
        json_path = temp / "truth_archive.json"
        json_path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n")
        with (temp / "truth_archive.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for post in ordered:
                writer.writerow({**post, "media": "; ".join(post.get("media", []))})
        with (temp / "post_provenance.jsonl").open("w", encoding="utf-8") as handle:
            for post in ordered:
                first, last, occurrences, changes = provenance[post["id"]]
                record = {
                    "id": post["id"], "first_snapshot": snapshots[first],
                    "selected_snapshot": snapshots[last],
                    "snapshot_occurrences": occurrences,
                    "record_changes_observed": changes,
                    "record_sha256": hashlib.sha256(json.dumps(
                        post, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                    ).encode()).hexdigest(),
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        with (temp / "source_snapshots.jsonl").open("w", encoding="utf-8") as handle:
            for summary in summaries:
                handle.write(json.dumps(summary) + "\n")
        report["files_sha256"] = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in temp.iterdir()
        }
        (temp / "recovery_report.json").write_text(json.dumps(report, indent=2) + "\n")
        # Publish only after every snapshot has been read and all files written.
        temp.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).parent)
    parser.add_argument("--revision", default="origin/main")
    parser.add_argument("--output", type=Path, default=Path("data/cumulative"))
    parser.add_argument("--fetch-missing", action="store_true")
    args = parser.parse_args()
    report = recover(args.repo, args.revision, args.output, args.fetch_missing)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
