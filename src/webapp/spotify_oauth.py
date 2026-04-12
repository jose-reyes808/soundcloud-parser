from __future__ import annotations

import base64
import secrets
import time
from typing import Any
from urllib.parse import quote, urlencode

import requests

from src.models import SpotifyTokens, WebAppConfig


class SpotifyOAuthService:
    AUTH_BASE_URL = "https://accounts.spotify.com/authorize"
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    API_BASE_URL = "https://api.spotify.com/v1"

    def __init__(self, config: WebAppConfig) -> None:
        self.config = config

    def build_authorize_url(self, state: str) -> str:
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

    def exchange_code(self, code: str) -> SpotifyTokens:
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

    def refresh_tokens(self, refresh_token: str) -> SpotifyTokens:
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
        response = requests.get(
            f"{self.API_BASE_URL}/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=self.config.request_timeout,
        )
        response.raise_for_status()
        return response.json()

    def generate_state(self) -> str:
        return secrets.token_urlsafe(32)

    def _build_token_headers(self) -> dict[str, str]:
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
        expires_in = int(payload.get("expires_in", 0))
        return SpotifyTokens(
            access_token=str(payload["access_token"]),
            refresh_token=str(payload["refresh_token"]) if payload.get("refresh_token") else None,
            expires_at=int(time.time()) + expires_in,
        )
