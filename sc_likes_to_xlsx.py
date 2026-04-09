import requests
import pandas as pd
from datetime import datetime
import time
import re

# --- CONFIG --- #
SOUNDCLOUD_CLIENT_ID = 'EsIST4DWFy7hEa8mvPoVwdjZ4NTZqmei'
SOUNDCLOUD_USER_ID = '58829397'

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://soundcloud.com/",
    "Origin": "https://soundcloud.com",
    "Accept-Language": "en-US,en;q=0.9"
}


def parse_title(title, uploader):
    if not title:
        return uploader, "", "SoundCloud User"

    title = title.strip()

    # Remove promotional junk like
    title = re.sub(r"\*.*?\*", "", title).strip()

    # Normalize dash types (en dash / em dash → hyphen)
    title = re.sub(r"[–—]", "-", title)

    # Split only on first hyphen
    parts = re.split(r"\s*-\s*", title, maxsplit=1)

    if len(parts) == 2:
        artist = parts[0].strip()
        song = parts[1].strip()
    else:
        artist = uploader
        song = title.strip()

    return artist, song, "Parsed"


def get_likes(client_id, user_id, backup_every=100):
    print("Fetching liked tracks...")
    likes = []

    url = f"https://api-v2.soundcloud.com/users/{user_id}/likes?client_id={client_id}&limit=200&offset=0"

    while url:

        # --- REQUEST WITH RETRIES ---
        for attempt in range(3):
            res = requests.get(url, headers=headers)

            if res.status_code == 200:
                break

            if res.status_code == 429:
                print("Rate limited. Sleeping 30s...")
                time.sleep(30)

            elif res.status_code == 401:
                print("401 received. Retrying after short delay...")
                time.sleep(5)

            else:
                print(f"HTTP {res.status_code} — retry {attempt + 1}/3")
                time.sleep(5)
        else:
            print("Failed page after retries — stopping pagination")
            return likes

        data = res.json()

        print("Loaded:", len(data.get("collection", [])))

        # --- PARSE TRACKS ---
        for item in data.get("collection", []):
            track = item.get("track")

            if not track:
                continue

            title = track.get("title", "")
            artist_field = track.get("artist")
            user = track.get("user", {})
            uploader = user.get("username", "Unknown")

            if artist_field:
                artist = artist_field
                song = title
                source = "API Artist Field"
            else:
                artist, song, source = parse_title(title, uploader)

            likes.append({
                "Artist": artist,
                "Song": song,
                "Artist Source": source,
                "Original Title": title,
                "Date Uploaded": track.get("created_at"),
                "Date Liked": item.get("created_at"),
                "SoundCloud URL": track.get("permalink_url")
            })

        # --- PAGINATION FIX (IMPORTANT) ---
        next_href = data.get("next_href")

        if next_href:
            if "client_id=" not in next_href:
                next_href += f"&client_id={client_id}"
            url = next_href
        else:
            url = None

        print("Next page:", bool(url))
        time.sleep(1)

    print("DEBUG total likes:", len(likes))
    return likes


def main():
    likes = get_likes(SOUNDCLOUD_CLIENT_ID, SOUNDCLOUD_USER_ID)

    print(f"Pages completed. Total likes collected: {len(likes)}")

    if len(likes) > 0:
        df = pd.DataFrame(likes)

        # Clean datetime columns
        for col in ['Date Uploaded', 'Date Liked']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.tz_localize(None)

        df.to_excel("soundcloud_likes.xlsx", index=False)

        print(len(likes))
        print(df["SoundCloud URL"].nunique())

        print(f"Done. Saved {len(df)} tracks.")
    else:
        print("No likes fetched (unexpected).")


if __name__ == "__main__":
    main()