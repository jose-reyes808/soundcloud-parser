from __future__ import annotations

"""Spotify Web API wrapper used by the FastAPI app and worker."""

import time
from typing import Any, Callable

import requests

from src.models import SpotifyTokens

# The web app needs token refresh semantics that are coupled to persisted job
# state, which is why this client is separate from the older CLI client.
class SpotifyApiClient:
    """Issue authenticated Spotify API requests using stored web-app tokens."""

    API_BASE_URL = "https://api.spotify.com/v1"

    def __init__(
        self,
        tokens: SpotifyTokens,
        refresh_tokens: Callable[[str], SpotifyTokens],
        persist_tokens: Callable[[SpotifyTokens], None],
        request_timeout: int = 30,
    ) -> None:
        """Store token state and the callbacks needed to refresh it safely."""

        self.tokens = tokens
        self.refresh_tokens = refresh_tokens
        self.persist_tokens = persist_tokens
        self.request_timeout = request_timeout

    # Search is the hot path of the import, so the method stays small and
    # delegates token management to the lower request helper.
    def search_tracks(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search Spotify for candidate tracks to match against one SoundCloud row."""

        response = self._request(
            "GET",
            "/search",
            params={
                "q": query,
                "type": "track",
                "limit": limit,
            },
        )
        return response.json().get("tracks", {}).get("items", [])

    def create_playlist(
        self,
        name: str,
        description: str = "",
        public: bool = False,
    ) -> dict[str, Any]:
        """Create a playlist for the authenticated Spotify account."""

        response = self._request(
            "POST",
            "/me/playlists",
            json={
                "name": name,
                "description": description,
                "public": public,
            },
        )
        return response.json()

    def add_items_to_playlist(self, playlist_id: str, uris: list[str]) -> None:
        """Add matched track URIs to a playlist in Spotify's allowed batch size."""

        for start_index in range(0, len(uris), 100):
            chunk = uris[start_index : start_index + 100]
            self._request(
                "POST",
                f"/playlists/{playlist_id}/tracks",
                json={"uris": chunk},
            )

    # Centralizing request behavior keeps refresh logic consistent across
    # search, playlist creation, and playlist population.
    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> requests.Response:
        """Send a Spotify request and transparently refresh expired credentials."""

        self._ensure_valid_access_token()
        response = requests.request(
            method=method,
            url=f"{self.API_BASE_URL}{path}",
            headers={"Authorization": f"Bearer {self.tokens.access_token}"},
            params=params,
            json=json,
            timeout=self.request_timeout,
        )

        if response.status_code == 401 and self.tokens.refresh_token:
            self.tokens = self.refresh_tokens(self.tokens.refresh_token)
            self.persist_tokens(self.tokens)
            response = requests.request(
                method=method,
                url=f"{self.API_BASE_URL}{path}",
                headers={"Authorization": f"Bearer {self.tokens.access_token}"},
                params=params,
                json=json,
                timeout=self.request_timeout,
            )

        response.raise_for_status()
        return response

    # Refreshing slightly early reduces the chance of an import failing midway
    # through a long run because a token expired during an API burst.
    def _ensure_valid_access_token(self) -> None:
        """Refresh the access token shortly before it expires."""

        if time.time() < self.tokens.expires_at - 60:
            return

        if not self.tokens.refresh_token:
            raise ValueError("Spotify access token expired and no refresh token is available.")

        self.tokens = self.refresh_tokens(self.tokens.refresh_token)
        self.persist_tokens(self.tokens)
