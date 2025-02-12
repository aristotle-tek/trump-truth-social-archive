import requests
import json
import os
import time
import csv

# Constants
OUTPUT_JSON_FILE = "./data/truth_archive.json"
OUTPUT_CSV_FILE = "./data/truth_archive.csv"
API_URL = "https://thorin-us-east-1.searchly.com/trump_tweets/_msearch?"
HEADERS = {
    "accept": "application/json",
    "authorization": "Basic cHVibGljLWtleTptZnB6c3JoZGR2bTdmNTRjdG90bmpiaHFjenUwejM1dA==",
    "content-type": "application/x-ndjson",
}

SAVE_EVERY = 1000  # Save every 1000 posts

def fetch_posts(offset=0, batch_size=25):
    """
    Fetches posts from the Trump Twitter/Truth Archive API.
    """
    request_body = (
        '{"preference":"results"}\n'
        '{"query":{"bool":{"must":[{"bool":{"must":[{"bool":{"boost":1,"minimum_should_match":1,"should":[{"term":{"isTS":"true"}}]}}]}}]}}},'
        '"size":' + str(batch_size) + ','
        '"_source":{"includes":["*"],"excludes":[]},'
        '"from":' + str(offset) + ','
        '"sort":[{"date":{"order":"desc"}}]}}\n'
    )


    try:
        response = requests.post(API_URL, headers=HEADERS, data=request_body)
        response.raise_for_status()
        data = response.json()

        if "responses" not in data or not data["responses"]:
            print(f"❌ No 'responses' field in API response at offset {offset}. Stopping.")
            return None

        hits = data["responses"][0].get("hits", {}).get("hits", [])

        if not hits:
            print(f"✅ No more posts found at offset {offset}. Stopping.")
            return None

        return hits

    except requests.RequestException as e:
        print(f"❌ Error fetching posts at offset {offset}: {e}")
        return None

def save_json(data, file_path):
    """
    Saves the full dataset to a JSON file.
    """
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def save_csv(data, file_path):
    """
    Saves the dataset to a CSV file.
    """
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "date", "content", "url", "favorites", "retweets"])  # Header row

        for post in data:
            writer.writerow([
                post["id"],
                post["date"],
                post["content"],
                post["url"],
                post["favorites"],
                post["retweets"],
            ])

def main():
    """
    Fetches all posts in batches and saves them to disk periodically.
    """
    all_posts = []
    offset = 0
    batch_size = 25
    save_counter = 0

    while True:
        print(f"Fetching posts {offset} to {offset + batch_size}...")
        posts = fetch_posts(offset, batch_size)

        if not posts:
            break  # Stop if no posts are retrieved

        for post in posts:
            post_data = post["_source"]
            all_posts.append({
                "id": post_data["id"],
                "date": post_data["date"],
                "content": post_data["text"],
                "url": f"https://truthsocial.com/@realDonaldTrump/{post_data['id']}",
                "favorites": post_data.get("favorites", 0),
                "retweets": post_data.get("retweets", 0),
            })

        offset += batch_size
        save_counter += batch_size

        # Save every 1000 posts
        if save_counter >= SAVE_EVERY:
            save_json(all_posts, OUTPUT_JSON_FILE)
            save_csv(all_posts, OUTPUT_CSV_FILE)
            print(f"💾 Saved {len(all_posts)} posts so far.")
            save_counter = 0  # Reset counter

        time.sleep(1)  # Prevent rate-limiting

    # Final save at the end
    save_json(all_posts, OUTPUT_JSON_FILE)
    save_csv(all_posts, OUTPUT_CSV_FILE)
    print(f"✅ Fetch complete. Saved {len(all_posts)} posts to {OUTPUT_JSON_FILE} and {OUTPUT_CSV_FILE}.")

if __name__ == "__main__":
    main()