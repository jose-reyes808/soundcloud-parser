from __future__ import annotations

import time

import requests

from models import TrackRecord
from parser import SoundCloudTitleParser


class SoundCloudClient:
    BASE_URL = "https://api-v2.soundcloud.com"

    def __init__(
        self,
        client_id: str,
        user_id: str,
        title_parser: SoundCloudTitleParser,
        page_limit: int = 200,
        request_timeout: int = 30,
    ) -> None:
        self.client_id = client_id
        self.user_id = user_id
        self.title_parser = title_parser
        self.page_limit = page_limit
        self.request_timeout = request_timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://soundcloud.com/",
            "Origin": "https://soundcloud.com",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def get_likes(self) -> list[TrackRecord]:
        print("Fetching liked tracks...")
        likes: list[TrackRecord] = []
        next_url = (
            f"{self.BASE_URL}/users/{self.user_id}/likes"
            f"?client_id={self.client_id}&limit={self.page_limit}&offset=0"
        )

        while next_url:
            response = self._get_with_retries(next_url)
            if response is None:
                print("Failed page after retries. Stopping pagination.")
                return likes

            payload = response.json()
            collection = payload.get("collection", [])
            print(f"Loaded: {len(collection)}")

            likes.extend(self._parse_collection(collection))

            next_url = payload.get("next_href")
            if next_url and "client_id=" not in next_url:
                next_url = f"{next_url}&client_id={self.client_id}"

            print(f"Next page: {bool(next_url)}")
            time.sleep(1)

        print(f"Total likes fetched: {len(likes)}")
        return likes

    def _get_with_retries(self, url: str) -> requests.Response | None:
        for attempt in range(1, 4):
            response = requests.get(
                url,
                headers=self.headers,
                timeout=self.request_timeout,
            )

            if response.status_code == 200:
                return response

            if response.status_code == 429:
                print("Rate limited. Sleeping 30 seconds before retrying.")
                time.sleep(30)
                continue

            if response.status_code == 401:
                print("Received 401. Sleeping 5 seconds before retrying.")
                time.sleep(5)
                continue

            print(f"HTTP {response.status_code}. Retry {attempt}/3")
            time.sleep(5)

        return None

    def _parse_collection(self, collection: list[dict]) -> list[TrackRecord]:
        parsed_records: list[TrackRecord] = []

        for item in collection:
            track = item.get("track")
            if not track:
                continue

            raw_title = track.get("title", "")
            user = track.get("user", {})
            uploader = user.get("username", "Unknown")
            artist, song, source = self.title_parser.parse_title(raw_title, uploader)

            parsed_records.append(
                TrackRecord(
                    artist=artist,
                    song=song,
                    artist_source=source,
                    original_title=raw_title,
                    date_uploaded=track.get("created_at"),
                    date_liked=item.get("created_at"),
                    soundcloud_url=track.get("permalink_url"),
                )
            )

        return parsed_records
