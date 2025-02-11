# Trump Truth Social archive scraper

This repository contains a Python script that scrapes posts from Donald Trump's Truth Social account and stores them in JSON and CSV formats. The scraper runs hourly via a GitHub Actions workflow and updates an S3 archive to keep a historical record of the posts. 

## How it works

### Fetching data from Truth Social API

The script (`scraper.py`) fetches posts directly from the Truth Social API using a proxy service (`ScrapeOps`) to bypass Cloudflare protections.

- **Pagination support:** It requests up to 100 new posts in batches of 20.
- **Media extraction:** Any images or videos in a post are extracted and stored as an array of URLs.
- **Duplicate handling:** Before adding new posts, the script checks an existing archive to avoid duplicates.

## Data output format

The scraper outputs posts in JSON format with the following structure:

```json
[
  {
    "id": "113986642361079256",
    "created_at": "2025-02-11T18:22:11.732Z",
    "content": "",
    "url": "https://truthsocial.com/@realDonaldTrump/113986642361079256",
    "media": ["https://truth-archive.us-iad-1.linodeobjects.com/attachments/12044/463ab1eb1bb9f326.mp4"]
  },
  {
    "id": "113986285138546896",
    "created_at": "2025-02-11T16:51:20.947Z",
    "content": "I am pleased to announce that Terry Cole will be the next Drug Enforcement Administration (DEA) administrator...",
    "url": "https://truthsocial.com/@realDonaldTrump/113986285138546896",
    "media": []
  }
]
```

### Fields explained

- **`id`** → The unique identifier for the post
- **`created_at`** → Timestamp when the post was made
- **`content`** → The text content of the post
- **`url`** → Direct link to the post on Truth Social
- **`media`** → An array of image and video URLs if the post contains media

## GitHub Actions automation

The scraper runs every hour at 47 minutes past using a GitHub Actions workflow and environment secrets for AWS and ScrapeOps. In addition to fetching the data, the workflow also copies it to a designated S3 bucket.

### Workflow steps

1. Clone the repository
2. Set up Python and install required dependencies
3. Run `scraper.py` to fetch the latest posts
4. Save new posts and update `truth_archive.json`
5. Upload the updated JSON file to an S3 bucket (`stilesdata.com/trump-truth-social-archive/`)
6. Commit and push changes back to GitHub

## Installation and running locally

To run the scraper manually on your machine:

### Install dependencies

```bash
pip install -r requirements.txt
```

### Set environment variables

You'll need to export your ScrapeOps API key and AWS credentials:

```bash
export SCRAPE_PROXY_KEY="your_scrapeops_api_key"
export AWS_ACCESS_KEY_ID="your_aws_key"
export AWS_SECRET_ACCESS_KEY="your_aws_secret"
```

### Run the scraper

```bash
python scraper.py
```

This will fetch new posts and update `truth_archive.json` and `truth_archive.csv`.

## Deployment

The script is fully automated via GitHub Actions. To update or change the workflow:

- Modify `.github/workflows/trump-truth-social-archive.yml`
- Push changes to GitHub
- The workflow will execute on the next scheduled run

## Data storage and access

- Historical posts are stored in an S3 bucket:
  - [`truth_archive.json`](https://stilesdata.com/trump-truth-social-archive/truth_archive.json)
  - [`truth_archive.csv`](https://stilesdata.com/trump-truth-social-archive/truth_archive.csv)

- The latest version of these files is also stored in this repo and updated regularly.

## Notes

This project is for archival and research purposes only. Use responsibly. It is not affiliated with my employer. requests
beautifulsoup4

### Next steps and improvements:

- Fetch replies and interactions on posts
- Improve media handling (support for more formats)
- Implement error logging for better monitoring