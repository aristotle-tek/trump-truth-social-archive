import requests
import json
import os
import time
import csv
import re
from html import unescape
from datetime import datetime
from pathlib import Path
import tempfile

# Load credentials from environment variables
SCRAPEOPS_API_KEY = os.getenv("SCRAPE_PROXY_KEY")
SCRAPEOPS_ENDPOINT = "https://proxy.scrapeops.io/v1/"
OUTPUT_JSON_FILE = "./data/truth_archive.json"
OUTPUT_CSV_FILE = "./data/truth_archive.csv"
RECOVERY_JSON_FILE = "./data/cumulative/truth_archive.json"
BASE_URL = "https://truthsocial.com/api/v1/accounts/107780257626128497/statuses"

def scrape(url, headers=None):
    """
    Makes a GET request to the target URL through the ScrapeOps proxy.
    """
    if not SCRAPEOPS_API_KEY:
        raise ValueError("Missing SCRAPE_PROXY_KEY environment variable")

    session = requests.Session()
    if headers:
        session.headers.update(headers)

    proxy_params = {
        'api_key': SCRAPEOPS_API_KEY,
        'url': url, 
        'bypass': 'cloudflare_level_1'
    }

    response = session.get(SCRAPEOPS_ENDPOINT, params=proxy_params, timeout=120)
    response.raise_for_status()

    return response.json()

def load_existing_posts():
    """
    Continue the cumulative archive; use older sources only for initial setup.
    """
    for file_path in (OUTPUT_JSON_FILE, RECOVERY_JSON_FILE):
        if Path(file_path).exists():
            with open(file_path, encoding="utf-8") as handle:
                records = json.load(handle)
            print(f"Loaded local archive: {file_path}")
            break
    else:
        raise FileNotFoundError("No local archive found. Restore data/truth_archive.json or run recovery first.")
    if not isinstance(records, list) or not records:
        raise ValueError("Existing archive must be a nonempty JSON array")
    existing_posts = {}
    for post in records:
        if not isinstance(post, dict) or not str(post.get("id", "")).isdigit() or not post.get("created_at"):
            raise ValueError("Invalid record in existing archive; refusing to overwrite it")
        post["id"] = str(post["id"])
        existing_posts[post["id"]] = post
    return existing_posts


def save_archive(data):
    """Prepare both outputs before replacing the cumulative files."""
    json_path, csv_path = Path(OUTPUT_JSON_FILE), Path(OUTPUT_CSV_FILE)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".scrape-", dir=json_path.parent) as temp:
        new_json, new_csv = Path(temp) / "archive.json", Path(temp) / "archive.csv"
        append_to_json_file(data, new_json)
        append_to_csv_file(data, new_csv)
        os.replace(new_json, json_path)
        os.replace(new_csv, csv_path)

def append_to_json_file(data, file_path):
    """
    Saves the full dataset to JSON (array format).
    """
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def append_to_csv_file(data, file_path):
    """
    Saves the dataset to a CSV file, including engagement metrics.
    """
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["id", "created_at", "content", "url", "media", "replies_count", "reblogs_count", "favourites_count"])
        for post in data:
            media_urls = "; ".join(post.get("media", []))
            writer.writerow([
                post.get("id"),
                post.get("created_at"),
                post.get("content", ""),
                post.get("url"),
                media_urls,
                post.get("replies_count", ""),
                post.get("reblogs_count", ""),
                post.get("favourites_count", "")
            ])

def clean_html(raw_html):
    """
    Removes HTML tags from a string.
    This strips unwanted markup like anchor tags.
    """
    return unescape(re.sub('<.*?>', '', raw_html))

def extract_posts(json_response, existing_posts):
    """
    Extracts relevant data from the JSON response, including engagement metrics.
    Clean HTML while preserving the Unicode already decoded from JSON.
    """
    extracted_data = []
    
    for post in json_response:
        post_id = post.get("id")
        if post_id in existing_posts:
            continue  # Skip duplicates

        media_urls = [media.get("url", "") for media in post.get("media_attachments", [])]

        extracted_data.append({
            "id": post_id,  # Needed for pagination
            "created_at": post.get("created_at"),
            "content": clean_html(post.get("content", "")).strip(),
            "url": post.get("url"),
            "media": media_urls,  # Store media in an array
            "replies_count": post.get("replies_count", 0),  # Number of replies
            "reblogs_count": post.get("reblogs_count", 0),  # Number of reblogs (shares)
            "favourites_count": post.get("favourites_count", 0)  # Number of likes
        })

    return extracted_data

def fetch_posts(max_pages=50):
    """
    Fetches posts with pagination up to a specified number of pages.
    """
    headers = {
        'accept': 'application/json, text/plain, */*',
        'referer': 'https://truthsocial.com/@realDonaldTrump'
    }
    
    params = {
        "exclude_replies": "true",
        "only_replies": "false",
        "with_muted": "true",
        "limit": "20"
    }

    existing_posts = load_existing_posts()
    page_count = 0
    new_post_count = 0
    seen_cursors = set()

    while page_count < max_pages:
        url = f"{BASE_URL}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
        print(f"Fetching: {url}")

        response = scrape(url, headers=headers)
        if not isinstance(response, list):
            raise ValueError("Truth Social response must be a JSON array")
        if not response:
            print("✅ Reached the end of the available posts.")
            break
        for post in response:
            if not isinstance(post, dict) or not str(post.get("id", "")).isdigit() or not post.get("created_at"):
                raise ValueError("Invalid post in Truth Social response")
            post["id"] = str(post["id"])
        new_posts = extract_posts(response, existing_posts)
        if not new_posts:
            print("✅ No new posts found. Exiting pagination.")
            break
        for post in new_posts:
            if post["id"] not in existing_posts:
                existing_posts[post["id"]] = post
                new_post_count += 1
        # Use the full page, including already-known posts, for the next cursor.
        cursor = str(min(int(post["id"]) for post in response))
        if cursor in seen_cursors:
            raise RuntimeError("Pagination did not advance; refusing to publish a partial scrape")
        seen_cursors.add(cursor)
        params["max_id"] = cursor
        page_count += 1
    else:
        raise RuntimeError(f"Reached {max_pages} pages before catching up; increase max_pages")

    # Sort posts in descending order by "created_at"
    all_posts = list(existing_posts.values())
    all_posts.sort(key=lambda post: datetime.fromisoformat(post["created_at"].replace("Z", "+00:00")), reverse=True)

    save_archive(all_posts)

    print(f"✅ Scraping complete. {new_post_count} new posts added; {len(all_posts)} total.")

if __name__ == "__main__":
    fetch_posts()
