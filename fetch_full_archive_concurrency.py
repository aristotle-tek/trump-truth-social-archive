import requests
import json
import os
import time
import csv
import concurrent.futures
from tqdm import tqdm

# Load credentials from environment variables
SCRAPEOPS_API_KEY = os.getenv("SCRAPE_PROXY_KEY")
SCRAPEOPS_ENDPOINT = "https://proxy.scrapeops.io/v1/"
OUTPUT_JSON_FILE = "./data/truth_archive_full.json"
OUTPUT_CSV_FILE = "./data/truth_archive_full.csv"
BASE_URL = "https://truthsocial.com/api/v1/accounts/107780257626128497/statuses"
CONCURRENT_REQUESTS = 5  # ScrapeOps allows 5 concurrent requests

def scrape(url, headers=None):
    """ Makes a GET request through the ScrapeOps proxy. """
    if not SCRAPEOPS_API_KEY:
        raise ValueError("Missing SCRAPE_PROXY_KEY environment variable")

    session = requests.Session()
    if headers:
        session.headers.update(headers)

    proxy_params = {
        'api_key': SCRAPEOPS_API_KEY,
        'url': url,
        'render_js': True,
        'bypass': 'cloudflare_level_1'
    }

    response = session.get(SCRAPEOPS_ENDPOINT, params=proxy_params, timeout=120)
    response.raise_for_status()
    
    return response.json()

def load_existing_posts():
    """ Loads existing archive and finds the oldest post ID we have. """
    if not os.path.exists(OUTPUT_JSON_FILE):
        return [], None

    try:
        with open(OUTPUT_JSON_FILE, "r", encoding="utf-8") as f:
            existing_posts = json.load(f)

        if not existing_posts:
            return [], None

        oldest_post_id = existing_posts[-1]["id"]  # Get the oldest post ID
        print(f"📌 Oldest post in archive: {oldest_post_id}")
        return existing_posts, oldest_post_id

    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"⚠️ Error reading archive: {e}. Starting fresh.")
        return [], None

def save_to_json(data, file_path):
    """ Saves the dataset to a JSON file. """
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def save_to_csv(data, file_path):
    """ Saves the dataset to a CSV file, including engagement metrics. """
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

def extract_posts(json_response):
    """ Extracts relevant data from the JSON response, including engagement metrics. """
    extracted_data = []
    
    for post in json_response:
        media_urls = [media.get("url", "") for media in post.get("media_attachments", [])]

        extracted_data.append({
            "id": post["id"],
            "created_at": post["created_at"],
            "content": post["content"].replace("<p>", "").replace("</p>", "").strip(),
            "url": post["url"],
            "media": media_urls,
            "replies_count": post.get("replies_count", 0),
            "reblogs_count": post.get("reblogs_count", 0),
            "favourites_count": post.get("favourites_count", 0)
        })

    return extracted_data

def fetch_posts_batch(max_ids):
    """ Fetches multiple pages concurrently given a list of max_ids. """
    headers = {
        'accept': 'application/json, text/plain, */*',
        'referer': 'https://truthsocial.com/@realDonaldTrump'
    }

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_REQUESTS) as executor:
        future_to_id = {
            executor.submit(scrape, f"{BASE_URL}?exclude_replies=true&only_replies=false&with_muted=true&limit=20&max_id={max_id}", headers): max_id
            for max_id in max_ids
        }

        for future in tqdm(concurrent.futures.as_completed(future_to_id), total=len(max_ids), desc="Fetching posts"):
            try:
                response = future.result()
                new_posts = extract_posts(response)
                if new_posts:
                    results.extend(new_posts)
            except Exception as e:
                print(f"❌ Error fetching batch {future_to_id[future]}: {e}")

    return results

def fetch_missing_posts():
    """
    Fetches missing posts, starting from the oldest archived post.
    Uses concurrent requests for efficiency.
    """
    existing_posts, oldest_post_id = load_existing_posts()
    all_posts = existing_posts[:]
    request_count = 0
    max_ids = [oldest_post_id] if oldest_post_id else []

    print("🔄 Fetching older posts with concurrency...")

    with tqdm(desc="Fetching requests", unit="requests") as progress_bar:
        while max_ids:
            # Fetch posts in parallel batches
            new_posts = fetch_posts_batch(max_ids)

            if not new_posts:
                print("✅ No more older posts found. Archive is complete.")
                break

            # Sort new posts (most recent first) & extend archive
            new_posts.sort(key=lambda post: post["created_at"], reverse=True)
            all_posts.extend(new_posts)

            # Prepare next batch of max_ids for concurrent fetching
            max_ids = [post["id"] for post in new_posts[-CONCURRENT_REQUESTS:]]  # Fetch older posts
            request_count += len(new_posts)
            progress_bar.update(len(new_posts))

            print(f"🔄 Request batch {request_count} complete. Next max_ids: {max_ids}")

            # Sleep to avoid excessive server load
            time.sleep(1)

    # Save updated archive
    save_to_json(all_posts, OUTPUT_JSON_FILE)
    save_to_csv(all_posts, OUTPUT_CSV_FILE)

    print(f"✅ Archive update complete. Total posts saved: {len(all_posts)}.")

if __name__ == "__main__":
    fetch_missing_posts()