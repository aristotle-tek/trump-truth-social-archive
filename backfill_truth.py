# fill in the missing days from when the original repo started collecting (Oct 26, 2025), to where this repo action began working (Oct 31, 2025).

import os, sys, json, csv, time
from datetime import datetime, date
from urllib.parse import urlencode
from dateutil import parser as dtp
import requests
import argparse
from pathlib import Path

BASE = "https://proxy.scrapeops.io/v1/"
TS_HOST = "https://truthsocial.com"
USER = "realDonaldTrump"
KEY = os.getenv("SCRAPE_PROXY_KEY")

def sx(url, params=None):
    # wrap target URL for ScrapeOps; urlenc b/c target may have its own query
    q = {'api_key': KEY, 'url': url}
    if params: url = f"{url}?{urlencode(params)}"
    return requests.get(BASE, params=urlencode({'api_key': KEY, 'url': url}), timeout=120)

def get_account_id():
    # try lookup; fallback to search (some servers disable lookup)
    r = sx(f"{TS_HOST}/api/v1/accounts/lookup", {'acct': USER})
    if r.status_code == 200:
        try:
            return r.json()['id']
        except Exception:
            pass
    r = sx(f"{TS_HOST}/api/v1/search", {'q': f"@{USER}", 'resolve': 'true', 'type': 'accounts', 'limit': 1})
    r.raise_for_status()
    accts = r.json().get('accounts', [])
    for a in accts:
        if (a.get('acct') or '').lower() == USER.lower() or (a.get('username') or '').lower() == USER.lower():
            return a['id']
    raise RuntimeError("Could not resolve account id")

def map_status(s):
    # keep fields in repo’s shape; media: list of URLs
    media_urls = [m.get('url') for m in s.get('media_attachments', []) if m.get('url')]
    return {
        'id': s['id'],
        'created_at': s['created_at'],
        'content': s.get('content', '') or '',
        'url': s.get('url') or f"{TS_HOST}/@{USER}/{s['id']}",
        'media': media_urls,
        'replies_count': s.get('replies_count', 0),
        'reblogs_count': s.get('reblogs_count', 0),
        'favourites_count': s.get('favourites_count', 0),
    }

def iso_to_dt(z):
    # accepts 2025-03-09T10:41:28.605Z
    return dtp.isoparse(z)

def iter_statuses(account_id, max_pages=100):
    max_id = None
    for _ in range(max_pages):
        params = {'limit': 40}
        if max_id: params['max_id'] = max_id
        r = sx(f"{TS_HOST}/api/v1/accounts/{account_id}/statuses", params)
        if r.status_code == 404: break
        r.raise_for_status()
        page = r.json()
        if not page: break
        for s in page: yield s
        # Mastodon-style paging: go older by using the smallest id returned
        max_id = min(page, key=lambda x: int(x['id']))['id']

def load_json_if(path):
    if not Path(path).exists(): return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def write_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def merge_into_csv(csv_path, records):
    # attempts to preserve existing header order if file exists; else writes a std header
    hdr = ['id','created_at','content','url','media','replies_count','reblogs_count','favourites_count']
    rows = []
    if Path(csv_path).exists():
        with open(csv_path, newline='', encoding='utf-8') as f:
            rdr = csv.DictReader(f)
            hdr = rdr.fieldnames or hdr
            rows.extend(rdr)
    existing_ids = {r['id'] for r in rows if 'id' in r}
    for r in records:
        if r['id'] in existing_ids: continue
        row = {k: (','.join(r['media']) if k=='media' else r.get(k,'')) for k in hdr}
        # fill any missing cols if header had extras
        for k in hdr:
            if k not in row: row[k] = r.get(k, '')
        rows.append(row)
    # sort desc by created_at
    rows.sort(key=lambda x: x.get('created_at',''), reverse=True)
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=hdr)
        w.writeheader()
        w.writerows(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('start', help='YYYY-MM-DD (inclusive)')
    ap.add_argument('end', help='YYYY-MM-DD (inclusive)')
    ap.add_argument('--merge', action='store_true', help='merge into truth_archive.json')
    ap.add_argument('--csv', action='store_true', help='also update truth_archive.csv when merging')
    args = ap.parse_args()
    if not KEY: raise SystemExit("SCRAPE_PROXY_KEY not set")

    start_d = date.fromisoformat(args.start)
    end_d = date.fromisoformat(args.end)

    acct_id = get_account_id()
    out_name = f"backfill_{args.start}_{args.end}.jsonl"
    out_path = Path(out_name)

    grabbed = []
    for s in iter_statuses(acct_id, max_pages=400):  # plenty for 4 days
        d = iso_to_dt(s['created_at']).date()
        if d > end_d:  # still too new; keep paging
            continue
        if d < start_d:
            break
        grabbed.append(map_status(s))

    # write minimal artifact
    with open(out_path, 'w', encoding='utf-8') as f:
        for r in grabbed:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f"Wrote {len(grabbed)} posts -> {out_path}")

    if args.merge:
        jpath = Path('truth_archive.json')
        current = load_json_if(jpath)
        have = {r['id'] for r in current}
        new = [r for r in grabbed if r['id'] not in have]
        merged = new + current
        # sort desc by created_at
        merged.sort(key=lambda x: x['created_at'], reverse=True)
        write_json(jpath, merged)
        print(f"Merged {len(new)} new posts into {jpath}")
        if args.csv:
            merge_into_csv('truth_archive.csv', new)
            print("Updated truth_archive.csv")

if __name__ == "__main__":
    main()
