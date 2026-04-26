from __future__ import annotations

"""SoundCloud API wrapper used for creating user playlists from import results."""

import time
from typing import Any, Callable

import requests

from src.models import SoundCloudTokens


class SoundCloudApiClient:
    """Issue authenticated SoundCloud API requests using user OAuth tokens."""

    API_BASE_URL = "https://api.soundcloud.com"

    def __init__(
        self,
        tokens: SoundCloudTokens,
        refresh_tokens: Callable[[str], SoundCloudTokens],
        persist_tokens: Callable[[SoundCloudTokens], None],
        request_timeout: int = 30,
    ) -> None:
        """Store token state and the callbacks needed for refresh persistence."""

        self.tokens = tokens
        self.refresh_tokens = refresh_tokens
        self.persist_tokens = persist_tokens
        self.request_timeout = request_timeout

    def create_playlist(
        self,
        title: str,
        track_ids: list[str],
        description: str = "",
        sharing: str = "private",
    ) -> dict[str, Any]:
        """Create a SoundCloud playlist containing the provided track IDs."""

        response = self._request(
            "POST",
            "/playlists",
            json={
                "playlist": {
                    "title": title,
                    "description": description,
                    "sharing": sharing,
                    "tracks": [{"id": int(track_id)} for track_id in track_ids],
                }
            },
        )
        return response.json()

    def create_playlist_best_effort(
        self,
        title: str,
        track_ids: list[str],
        description: str = "",
        sharing: str = "private",
    ) -> tuple[dict[str, Any], list[str], list[str]]:
        """Create a playlist while skipping tracks SoundCloud refuses to accept.

        SoundCloud appears willing to create a playlist shell even when part of
        the submitted track set is invalid or restricted. For larger mixed sets
        like "exclusives", best-effort addition is safer than treating the
        whole list as all-or-nothing.
        """

        playlist = self.create_playlist(
            title=title,
            track_ids=[],
            description=description,
            sharing=sharing,
        )
        playlist_id = str(playlist["id"])

        accepted_ids: list[str] = []
        skipped_ids: list[str] = []

        def add_chunk(candidate_ids: list[str]) -> None:
            if not candidate_ids:
                return

            try:
                self.set_playlist_tracks(playlist_id, accepted_ids + candidate_ids)
                accepted_ids.extend(candidate_ids)
                return
            except requests.exceptions.HTTPError:
                if len(candidate_ids) == 1:
                    skipped_ids.extend(candidate_ids)
                    return

            midpoint = len(candidate_ids) // 2
            add_chunk(candidate_ids[:midpoint])
            add_chunk(candidate_ids[midpoint:])

        add_chunk(track_ids)
        playlist = self.get_playlist(playlist_id)
        return playlist, accepted_ids, skipped_ids

    def set_playlist_tracks(self, playlist_id: str, track_ids: list[str]) -> dict[str, Any]:
        """Replace the playlist's track list with the provided SoundCloud IDs."""

        response = self._request(
            "PUT",
            f"/playlists/{playlist_id}",
            json={
                "playlist": {
                    "tracks": [{"id": int(track_id)} for track_id in track_ids],
                }
            },
        )
        return response.json()

    def get_playlist(self, playlist_id: str) -> dict[str, Any]:
        """Fetch a playlist so the caller can inspect its final persisted state."""

        response = self._request("GET", f"/playlists/{playlist_id}")
        return response.json()

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> requests.Response:
        """Send a SoundCloud request and refresh credentials when needed."""

        self._ensure_valid_access_token()
        response = requests.request(
            method=method,
            url=f"{self.API_BASE_URL}{path}",
            headers={
                "Authorization": f"Bearer {self.tokens.access_token}",
                "accept": "application/json; charset=utf-8",
                "Content-Type": "application/json",
            },
            json=json,
            timeout=self.request_timeout,
        )

        if response.status_code == 401 and self.tokens.refresh_token:
            self.tokens = self.refresh_tokens(self.tokens.refresh_token)
            self.persist_tokens(self.tokens)
            response = requests.request(
                method=method,
                url=f"{self.API_BASE_URL}{path}",
                headers={
                    "Authorization": f"Bearer {self.tokens.access_token}",
                    "accept": "application/json; charset=utf-8",
                    "Content-Type": "application/json",
                },
                json=json,
                timeout=self.request_timeout,
            )

        response.raise_for_status()
        return response

    def _ensure_valid_access_token(self) -> None:
        """Refresh the SoundCloud access token shortly before it expires."""

        if time.time() < self.tokens.expires_at - 60:
            return

        if not self.tokens.refresh_token:
            raise ValueError("SoundCloud access token expired and no refresh token is available.")

        self.tokens = self.refresh_tokens(self.tokens.refresh_token)
        self.persist_tokens(self.tokens)
