import requests
import json
import os
import time
import csv
import re

# Load credentials from environment variables
SCRAPEOPS_API_KEY = os.getenv("SCRAPE_PROXY_KEY")
SCRAPEOPS_ENDPOINT = "https://proxy.scrapeops.io/v1/"
OUTPUT_JSON_FILE = "./data/truth_archive.json"
OUTPUT_CSV_FILE = "./data/truth_archive.csv"
ARCHIVE_URL = "https://stilesdata.com/trump-truth-social-archive/truth_archive.json"
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
    Loads existing posts from the archive.
    """
    try:
        response = requests.get(ARCHIVE_URL, timeout=30)
        response.raise_for_status()
        existing_posts = {post["id"]: post for post in response.json()}
        return existing_posts
    except requests.RequestException as e:
        print(f"⚠️ Warning: Could not fetch existing archive, starting fresh. Error: {e}")
        return {}

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
                post.get("replies_count", 0),
                post.get("reblogs_count", 0),
                post.get("favourites_count", 0)
            ])

def clean_html(raw_html):
    """
    Removes HTML tags from a string.
    This strips unwanted markup like anchor tags.
    """
    return re.sub('<.*?>', '', raw_html)

def fix_unicode(text):
    """
    Ensures that escaped Unicode sequences (e.g., \u2026, \u2014)
    are converted to their proper characters.
    """
    try:
        return text.encode('utf-8').decode('unicode_escape')
    except Exception:
        return text

def extract_posts(json_response, existing_posts):
    """
    Extracts relevant data from the JSON response, including engagement metrics.
    Applies clean_html and fix_unicode to the post content.
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
            "content": fix_unicode(clean_html(post.get("content", ""))).strip(),
            "url": post.get("url"),
            "media": media_urls,  # Store media in an array
            "replies_count": post.get("replies_count", 0),  # Number of replies
            "reblogs_count": post.get("reblogs_count", 0),  # Number of reblogs (shares)
            "favourites_count": post.get("favourites_count", 0)  # Number of likes
        })

    return extracted_data

def fetch_posts(max_pages=3):
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
    all_posts = list(existing_posts.values())  # Start with existing data
    page_count = 0
    new_posts = []

    while page_count < max_pages:
        url = f"{BASE_URL}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
        print(f"Fetching: {url}")

        try:
            response = scrape(url, headers=headers)
            if not response:  # Ensure response is valid
                print(f"⚠️ Empty response from {url}. Skipping.")
                continue

            new_posts = extract_posts(response, existing_posts)
            if not new_posts:
                print("✅ No new posts found. Exiting pagination.")
                break  # No more new posts

            all_posts.extend(new_posts)  # Merge new posts
            params["max_id"] = new_posts[-1]["id"]  # Get older posts
            page_count += 1

        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching posts: {e}")
            break

    # Sort posts in descending order by "created_at"
    all_posts.sort(key=lambda post: post["created_at"], reverse=True)

    append_to_json_file(all_posts, OUTPUT_JSON_FILE)  # Save the updated archive in JSON
    append_to_csv_file(all_posts, OUTPUT_CSV_FILE)  # Save the archive in CSV format

    print(f"✅ Scraping complete. {len(new_posts) if new_posts else 0} new posts added.")

if __name__ == "__main__":
    fetch_posts(max_pages=3)