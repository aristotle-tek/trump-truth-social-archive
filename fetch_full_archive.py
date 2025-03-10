import requests
import json
import os
import time
import csv
from tqdm import tqdm  # Import progress bar

# Load credentials from environment variables
SCRAPEOPS_API_KEY = os.getenv("SCRAPE_PROXY_KEY")
SCRAPEOPS_ENDPOINT = "https://proxy.scrapeops.io/v1/"
OUTPUT_JSON_FILE = "./data/truth_archive_full.json"
OUTPUT_CSV_FILE = "./data/truth_archive_full.csv"
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
        'render_js': True,
        'bypass': 'cloudflare_level_1'
    }

    response = session.get(SCRAPEOPS_ENDPOINT, params=proxy_params, timeout=120)
    response.raise_for_status()
    
    return response.json()

def save_to_json(data, file_path):
    """
    Saves the dataset to a JSON file.
    """
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def save_to_csv(data, file_path):
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

def extract_posts(json_response):
    """
    Extracts relevant data from the JSON response, including engagement metrics.
    """
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


def fetch_all_posts():
    """
    Fetches all posts, paginating until no more are found.
    Implements retry logic for empty responses and server errors.
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

    all_posts = []  # Start fresh with an empty archive
    request_count = 0  # Track the number of API requests
    pbar = tqdm(desc="Fetching posts", unit="requests", colour="blue")  # Initialize progress bar

    while True:
        url = f"{BASE_URL}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"

        retry_attempts = 3
        success = False

        for attempt in range(retry_attempts):
            try:
                response = scrape(url, headers=headers)
                
                if not response:  # If response is empty
                    print(f"⚠️ Empty response from API. Retrying in {2**attempt} sec...")
                    time.sleep(1**attempt)  # Exponential backoff: 2, 4, 8 sec
                    continue  # Retry request
                
                new_posts = extract_posts(response)
                if not new_posts:
                    print("\n✅ No more posts found. Archive is complete.")
                    pbar.close()  # Close progress bar
                    return  # Exit loop

                all_posts.extend(new_posts)
                params["max_id"] = new_posts[-1]["id"]  # Get older posts
                
                # ✅ Clean logging: Show request number instead of full URL
                request_count += 1
                pbar.set_description(f"Fetching request {request_count}")  # Update tqdm bar
                pbar.update(1)  # Increment request count in progress bar

                # Log only the most relevant updates
                print(f"🔄 Request {request_count} complete. Next max_id: {new_posts[-1]['id']}")

                success = True  # Request succeeded, exit retry loop
                break  # Exit retry loop
                
            except requests.exceptions.RequestException as e:
                print(f"❌ Error on attempt {attempt + 1}: {e}")
                time.sleep(1**attempt)  # Exponential backoff before retrying

        if not success:
            print("❌ Max retries reached. Moving to next page...")
            break  # Stop scraping if repeated failures occur

        # **Sleep between requests to prevent hitting rate limits**
        time.sleep(1)

    # Sort posts in descending order by "created_at"
    all_posts.sort(key=lambda post: post["created_at"], reverse=True)

    save_to_json(all_posts, OUTPUT_JSON_FILE)  # Save as a fresh JSON archive
    save_to_csv(all_posts, OUTPUT_CSV_FILE)  # Save as a fresh CSV archive

    pbar.close()  # Close tqdm progress bar
    print(f"\n✅ Full archive fetch complete. Saved {len(all_posts)} posts.")

if __name__ == "__main__":
    fetch_all_posts()