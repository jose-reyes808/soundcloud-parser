from __future__ import annotations

"""Server-side Spotify OAuth helpers for the web application."""

import base64
import secrets
import time
from typing import Any
from urllib.parse import quote, urlencode

import requests

from src.models import SpotifyTokens, WebAppConfig

# OAuth is subtle enough to deserve its own service boundary. Keeping it here
# prevents the route layer from accumulating protocol details and error cases.
class SpotifyOAuthService:
    """Build Spotify OAuth URLs and exchange codes for usable tokens."""

    AUTH_BASE_URL = "https://accounts.spotify.com/authorize"
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    API_BASE_URL = "https://api.spotify.com/v1"

    def __init__(self, config: WebAppConfig) -> None:
        """Store web-app OAuth settings sourced from environment configuration."""

        self.config = config

    # The authorize URL is generated centrally so scopes, redirect URIs, and
    # login behavior stay consistent across the app.
    def build_authorize_url(self, state: str) -> str:
        """Build the Spotify login URL for a specific anti-CSRF state token."""

        query = urlencode(
            {
                "client_id": self.config.spotify_client_id,
                "response_type": "code",
                "redirect_uri": self.config.spotify_redirect_uri,
                "scope": " ".join(self.config.spotify_scopes),
                "state": state,
                "show_dialog": "false",
            },
            quote_via=quote,
        )
        return f"{self.AUTH_BASE_URL}?{query}"

    # The callback uses this immediately after Spotify redirects back with a
    # one-time authorization code.
    def exchange_code(self, code: str) -> SpotifyTokens:
        """Exchange an authorization code for an access and refresh token pair."""

        response = requests.post(
            self.TOKEN_URL,
            headers=self._build_token_headers(),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.config.spotify_redirect_uri,
            },
            timeout=self.config.request_timeout,
        )
        response.raise_for_status()
        return self._build_tokens(response.json())

    # Long-running imports depend on refresh support because playlist creation
    # can outlive the initial access token.
    def refresh_tokens(self, refresh_token: str) -> SpotifyTokens:
        """Refresh a web-session token set without requiring a new login."""

        response = requests.post(
            self.TOKEN_URL,
            headers=self._build_token_headers(),
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=self.config.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if "refresh_token" not in payload:
            payload["refresh_token"] = refresh_token
        return self._build_tokens(payload)

    def get_current_user_profile(self, access_token: str) -> dict[str, Any]:
        """Fetch the current Spotify user's profile for display and auditing."""

        response = requests.get(
            f"{self.API_BASE_URL}/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=self.config.request_timeout,
        )
        response.raise_for_status()
        return response.json()

    def generate_state(self) -> str:
        """Generate a cryptographically strong OAuth state token."""

        return secrets.token_urlsafe(32)

    def _build_token_headers(self) -> dict[str, str]:
        """Create the Basic-auth header used by Spotify's token endpoint."""

        raw_credentials = (
            f"{self.config.spotify_client_id}:{self.config.spotify_client_secret}".encode("utf-8")
        )
        encoded_credentials = base64.b64encode(raw_credentials).decode("utf-8")
        return {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    @staticmethod
    def _build_tokens(payload: dict[str, Any]) -> SpotifyTokens:
        """Convert Spotify's token payload into the app's typed token model."""

        expires_in = int(payload.get("expires_in", 0))
        return SpotifyTokens(
            access_token=str(payload["access_token"]),
            refresh_token=str(payload["refresh_token"]) if payload.get("refresh_token") else None,
            expires_at=int(time.time()) + expires_in,
        )
