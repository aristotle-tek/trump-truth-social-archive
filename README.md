# Trump Truth Social archive scraper

This repository contains a Python script that scrapes posts from Donald Trump's Truth Social account and stores them in JSON and CSV formats. In this fork, a GitHub Actions workflow runs every four hours and commits the cumulative archive to the repository.

**Coverage comparison — November 12, 2026.** After reconciliation, this archive contains all **38,017 IDs in the checked CNN snapshot**, plus **5,015 IDs absent from that snapshot**. Of those additional records, 4,396 have other accounts' URLs and are not counted as evidence of additional original Trump-authored posts. The remaining **619 have Trump-account URLs; 618 were also found by exact Truth Social ID in Trump's Truth**. This supports a narrower claim of broader coverage of distinct archived IDs than that dated CNN snapshot. It does not establish a complete record of every original Trump post or 619 additional pieces of unique original content.

The comparison also found **216 CNN records missing here**, which were added with their source payloads and provenance. Of these, 211 were also found in Trump's Truth; five currently have CNN as their only corroborating source in this check. All **42,816 pre-existing records were preserved without field changes**, bringing the reconciled dataset to **43,032 records**. Exact IDs and source URLs were checked for duplication. Repeated text at distinct IDs can represent separate reposting events: 23 of our unmatched Trump-URL records share text with a CNN record and were not collapsed solely on that basis.

The check exposed **115 historical timestamp conflicts**, generally around four or five hours, between existing records and Trump's Truth. Existing timestamps were preserved, and the conflicts are listed for research use rather than silently corrected. The four previously flagged zero-post UTC dates were empty in our archive, CNN, and the fetched Trump's Truth windows; the latter returned posts on surrounding dates. No additional posts for those four dates were established by these checks. This agreement is not proof that no posting occurred.

The [reconciliation report](data/reconciliation/2026-11-12/report.json), [unmatched ID table](data/reconciliation/2026-11-12/unmatched_ids.csv), [imported source records](data/reconciliation/2026-11-12/imported_records.jsonl), and [timestamp conflicts](data/reconciliation/2026-11-12/timestamp_conflicts.csv) document the findings. The dated folder preserves the CNN JSON snapshot, compressed public RSS responses, requested URLs, corroborating archive links, and file checksums. CNN's feed is the successor advertised by the original maintainer; agreement between archives should not be assumed to represent fully independent collection. The [Trump's Truth FAQ](https://www.trumpstruth.org/faq) describes its date-filtered feed and caching limitations.

**This workflow was disabled on Oct. 26, 2025 in the original repo; I have re-started it (without the AWS bucket) in this fork on Oct 31, 2025. I tried to backfill the gap but be aware of possible changes during this period.**

**Data correction — November 2, 2026.** Earlier versions of this fork contained incomplete data because each scrape reloaded the original project's frozen archive instead of retaining this fork's previous results. The error was corrected in the November 2 update, and the archive was reconstructed from the repository's saved history. The reconstruction restored 42,358 unique archived records, including 12,889 IDs absent from the previous version. Subsequent collections add to that recovered dataset. Users who downloaded earlier versions should download the corrected files again.

**Catch-up verified — November 2, 2026.** The [first run of the corrected workflow](https://github.com/aristotle-tek/trump-truth-social-archive/actions/runs/41465263968) completed successfully at **14:48:12 UTC**. It retained all 42,358 recovered IDs and added **64 recent records**, bringing the archive to **42,422 records** at that point. The newest post returned was dated **November 2, 2026 at 06:52:32 UTC**. Pagination continued until it reached previously archived data, completing the catch-up for recent posts available through the API. Tests, archive validation, and the automatic data commit all passed. Historical coverage remains subject to the limitations below; this successful collection does not establish that every Truth Social post was originally captured.

Please cite this repository when using data collected after October 26, 2025.

## Recovered cumulative archive

The active downloads are [data/truth_archive.json](data/truth_archive.json) and [data/truth_archive.csv](data/truth_archive.csv). These existing paths now contain the recovered cumulative dataset and will receive future updates.

The recovery inspected 3,093 JSON/JSONL file-change snapshots across 4,137 commits reachable from `e8c7e721dc64b66eef87f680d8cb964c687e4aa7`. It produced **42,358 unique archived post IDs**, recovering **12,889 IDs** absent from the previous 29,469-record archive. Records span February 14, 2022 through November 1, 2026. The following files preserve the recovery snapshot and its evidence as prepared on November 2; future scraper runs do not modify them:

- [Cumulative JSON](data/cumulative/truth_archive.json)
- [Cumulative CSV](data/cumulative/truth_archive.csv)
- [Recovery counts, monthly coverage, and checksums](data/cumulative/recovery_report.json)
- [Source commit for each selected post](data/cumulative/post_provenance.jsonl)
- [Inventory of historical source snapshots](data/cumulative/source_snapshots.jsonl)
- [Independent validation results](data/cumulative/validation_report.json)
- [Daily archived post counts](data/cumulative/daily_post_counts.csv)

The old scraper loaded the original project's archive on every run. That archive stopped on October 25, 2025, so each run replaced the intervening history with at most 60 recent posts. The recovered dataset takes the union of IDs across historical snapshots, including the October 2025 backfills and posts present in older snapshots but subsequently absent. For repeated IDs, it retains the last record observed in topological commit order. Content, encoding, and engagement counts remain as stored in that record; this process does not update them from Truth Social.

The scraper reads and writes `data/truth_archive.json` and `.csv`. It retains existing IDs, paginates until it reaches an already archived page, and fails without replacing its outputs if fetching fails. It stops on an empty response and reports a failure if it reaches its 50-page limit before catching up. If the active JSON is absent, it can restore from the fixed recovery snapshot. If both local sources are absent, it stops. It no longer loads the frozen upstream archive. Historical incomplete versions remain in Git history.

The workflow runs tests and validates JSON/CSV agreement before and after scraping. The checks require every recovered ID to remain in the active dataset. Only the active JSON and CSV are committed by the automated job.

### Coverage and interpretation

The [daily coverage table](data/coverage/daily_coverage.csv) compares post creation dates with archive commit dates in UTC. The [coverage report](data/coverage/coverage_report.json) records the audit time and input revision. From October 31, 2025 through November 1, 2026, every complete UTC day had an archive commit. Four dates have no archived posts despite six archive commits on each date:

| UTC date | Archived posts | Archive commits |
| --- | ---: | ---: |
| 2025-11-13 | 0 | 6 |
| 2025-12-21 | 0 | 6 |
| 2025-12-29 | 0 | 6 |
| 2026-06-07 | 0 | 6 |

These dates warrant checking against another source. Commits show that archive files changed, not that every post was collected. A day with no commit can also reflect unchanged output. November 2 is a partial day and is excluded from the complete-day lists. The recent collection interruption was addressed by the verified catch-up run described above.

Of the recovered records, 37,962 have `@realDonaldTrump` URLs and 4,396 have other accounts' URLs. Other-account records may represent retruths or older source conventions; the flat stored fields do not reliably distinguish them. The archive preserves these records and their sources rather than discarding them. Its total should not be treated as a verified count of original Trump-authored posts. Engagement counts are absent for 4,525 records; CSV leaves these values blank rather than treating them as zero. Historical text and encoding are retained as stored. Newly collected text preserves Unicode characters.

To reproduce the recovery, use a clone with complete commit history and a new output directory:

```bash
# Only needed for a shallow clone; --filter avoids downloading unrelated files.
git fetch --unshallow --filter=blob:none --no-tags origin main
python recover_archive.py --revision e8c7e721dc64b66eef87f680d8cb964c687e4aa7 --output data/recovered-again --fetch-missing
python verify_recovery.py --output data/recovered-again --fetch-missing
python -m unittest discover -s tests -v
```

The verification checks JSON/CSV agreement, provenance checksums, historical CSV IDs, and selected records against their source Git objects. Recovery can retrieve records committed to this repository. It cannot recover posts that were never committed or fill dates after the newest archived post without fetching more data. The reports describe the reconstruction at the recorded revision; later scraper runs will change the active files while leaving the recovery snapshot unchanged.


## How it works

### Fetching data from Truth Social API

The script (`scrape.py`) fetches posts from the Truth Social API using the ScrapeOps proxy service.

- **Pagination support:** It requests batches of 20 until it reaches an archived page, with a limit of 50 pages per run.
- **Media extraction:** Any images or videos in a post are extracted and stored as an array of URLs.
- **Duplicate handling:** Before adding new posts, the script checks an existing archive to avoid duplicates.

## Data output format

The scraper outputs posts in JSON format with the following structure:

```json
[
  {
    "id": "114132050804394743",
    "created_at": "2025-03-09T10:41:28.605Z",
    "content": "Will be interviewed by Maria Bartiromo on Sunday Morning Futures at 10:00amET, enjoy! <span class=\"h-card\"><a href=\"https://truthsocial.com/@FoxNews\" class=\"u-url mention\">@<span>FoxNews</span></a></span>",
    "url": "https://truthsocial.com/@realDonaldTrump/114132050804394743",
    "media": [
      "https://static-assets-1.truthsocial.com/tmtg:prime-ts-assets/media_attachments/files/114/132/050/631/878/172/original/f0e7d14a580b0bc6.mp4"
    ],
    "replies_count": 925,
    "reblogs_count": 2938,
    "favourites_count": 13166
  },
  {
    "id": "114130744626893259",
    "created_at": "2025-03-09T05:09:17.893Z",
    "content": "",
    "url": "https://truthsocial.com/@realDonaldTrump/114130744626893259",
    "media": [
      "https://static-assets-1.truthsocial.com/tmtg:prime-ts-assets/media_attachments/files/114/130/744/449/958/273/original/56b8a2c4e789ede9.jpg"
    ],
    "replies_count": 2451,
    "reblogs_count": 3833,
    "favourites_count": 16848
  },
]
```

### Field descriptions

- **`id`** → The unique identifier for the post
- **`created_at`** → Timestamp when the post was made
- **`content`** → The text content of the post
- **`url`** → Direct link to the post on Truth Social
- **`media`** → An array of image and video URLs if the post contains media
- **`replies_count`** → Number of replies to Trump post
- **`reblogs_count`** → Number of re-posts, or re-truths, to Trump post
- **`favourites_count`** → Number of favorites to Trump post

## GitHub Actions automation

The scraper runs every four hours at 47 minutes past, using a GitHub Actions workflow and the `SCRAPE_PROXY_KEY` repository secret. This fork stores its output in Git and does not upload to S3.

*Note: I'm considering strategies now for periodically rehydrating the archive with updated engeagement analytics (re-posts, replies, etc.) so that we capture changes over time for popular posts.*

### Workflow steps

1. Clone the repository
2. Set up Python and install required dependencies
3. Run `scrape.py` to fetch the latest posts
4. Merge new posts into `data/truth_archive.json` and regenerate its CSV
5. Commit and push changes back to GitHub

## Installation and running locally

To run the scraper manually on your machine:

### Install dependencies

```bash
pip install -r requirements.txt
```

### Set environment variables

You'll need to export your ScrapeOps API key:

```bash
export SCRAPE_PROXY_KEY="your_scrapeops_api_key"
```

### Run the scraper

```bash
python scrape.py
```

This will fetch new posts and update `data/truth_archive.json` and `data/truth_archive.csv`.

## Deployment

The workflow uses Ubuntu 24.04 and Python 3.12, replacing the Python 3.9 / Ubuntu 26.04 combination that failed. Checkout, Python setup, and auto-commit are pinned to verified releases that use Node 24: `actions/checkout@v7.0.1`, `actions/setup-python@v7.1.0`, and `stefanzweifel/git-auto-commit-action@v7.2.1`.

Before publishing, run:

```bash
python3.12 -m unittest discover -s tests -v
python3.12 check_archive.py
```

Commit the code, active data, recovery snapshot, and audit reports together, then push to `main`. The local ZIP is a download bundle and is ignored by Git. There is no need to rerun recovery to publish the prepared files.

After pushing a workflow change, open **Actions → trump-truth-social-archive (no S3) → Run workflow**, choose **main**, and start a new run. Re-running an old failed run would use its old workflow revision. The repository needs the `SCRAPE_PROXY_KEY` Actions secret; it was verified by the successful live catch-up on November 2, 2026. The workflow already requests `contents: write` for its automatic data commit.

Confirm that tests, archive checks, scraping, and the automatic commit succeed. Inspect the scraper's new-post count, the newest `created_at` value, and the active dataset size. A successful catch-up should preserve all 42,358 recovered IDs and add any available recent posts. A green Python setup step alone does not establish successful collection. Record the run and its timestamps when investigating future interruptions. Scheduled runs continue every four hours. Future proxy or network failures can still occur; they should fail visibly and preserve the previous archive.

To repeat the quick checks and dated commit-coverage audit:

```bash
python3.12 check_archive.py
python3.12 check_archive.py --coverage-output data/coverage --revision origin/main
```

The second command requires complete Git history. These dated coverage reports are maintained manually; they are not updated by the scraper workflow.

## Data storage and access

- The active cumulative archive is stored at [`data/truth_archive.json`](data/truth_archive.json) and [`data/truth_archive.csv`](data/truth_archive.csv).
- The fixed recovery snapshot and provenance are stored under [`data/cumulative/`](data/cumulative/).
- The original project's frozen archive remains available from its S3 bucket:
  - [`truth_archive.json`](https://stilesdata.com/trump-truth-social-archive/truth_archive.json)
  - [`truth_archive.csv`](https://stilesdata.com/trump-truth-social-archive/truth_archive.csv)

- The scraper does not use that upstream archive. Earlier incomplete versions of this fork's active files remain available in Git history.

## Notes

This project is for archival and research purposes only. Use responsibly. It is not affiliated with my employer.

### Next steps and improvements:

- Better flags for original posts vs. retweets
- Better handling of media-only posts
- Improve media handling (support for more formats)
- Implement error logging for better monitoring
- Better analytics: Keywords, classification, etc. 
- Consider front-end display or Slack integration to help news teams monitor posts
