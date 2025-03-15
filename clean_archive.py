import os
import json
import re
import csv

# Try to import ftfy to robustly fix encoding issues
try:
    import ftfy
    def fix_unicode(text):
        return ftfy.fix_text(text)
except ImportError:
    # Fallback: attempt a simple conversion if ftfy isn't installed
    def fix_unicode(text):
        try:
            return text.encode('latin-1').decode('utf-8')
        except Exception:
            return text

def clean_html(text):
    """Remove HTML tags from the text."""
    return re.sub(r'<.*?>', '', text)

def process_post(post):
    """Clean a post's content by stripping HTML and fixing Unicode issues."""
    raw = post.get("content", "")
    # First remove HTML tags, then fix any encoding issues
    clean_text = fix_unicode(clean_html(raw)).strip()
    post["content"] = clean_text
    return post

def load_archive(file_path):
    """Load posts from a JSON archive."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(data, file_path):
    """Save cleaned data to a JSON file using actual Unicode characters."""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def save_csv(data, file_path):
    """Save cleaned data to a CSV file."""
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "created_at", "content", "url", "media",
            "replies_count", "reblogs_count", "favourites_count"
        ])
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

def main():
    # Define input and output file paths
    INPUT_JSON_FILE = "./src/data/truth_archive.json"
    OUTPUT_JSON_FILE = "./src/data/truth_archive_scrubbed.json"
    OUTPUT_CSV_FILE = "./src/data/truth_archive_scrubbed.csv"
    
    try:
        posts = load_archive(INPUT_JSON_FILE)
    except Exception as e:
        print(f"Error reading {INPUT_JSON_FILE}: {e}")
        return

    # Process each post to clean its content
    cleaned_posts = [process_post(post) for post in posts]
    
    # Save cleaned data to new JSON and CSV files
    save_json(cleaned_posts, OUTPUT_JSON_FILE)
    save_csv(cleaned_posts, OUTPUT_CSV_FILE)
    
    print("Archive scrubbed successfully.")
    print(f"JSON output: {OUTPUT_JSON_FILE}")
    print(f"CSV output:  {OUTPUT_CSV_FILE}")

if __name__ == "__main__":
    main()
