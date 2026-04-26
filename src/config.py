from __future__ import annotations

"""Configuration loading utilities for both local and web execution modes."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from src.models import AppConfig, ParserSettings, SpotifyConfig, WebAppConfig


DEFAULT_PAREN_KEYWORDS = [
    "remix",
    "edit",
    "flip",
    "bootleg",
    "rework",
    "vip",
    "ft.",
    "feat.",
    "mix",
    "switch up",
]

DEFAULT_LIVESET_KEYWORDS = [
    "live set",
    "full set",
    "bbc",
    "b2b",
    "mixtape",
    "live at",
    "festival set",
    "diplo & friends",
    "diplo and friends",
    "hard summer",
    "hsmf",
    "escape psycho circus",
    "edc",
    "holy ship",
    "benzi",
    "ultra music festival",
    "ultra 20",
    "ultra miami",
    "beyond wonderland",
    "mini mix",
    "hello festival season",
    "dia de los muertos",
    "halloween",
    "countdown",
    "this is fawks",
    "xs",
    "dtg",
    "caller id",
]

DEFAULT_CUTOFF_PATTERNS = [
    r"\bout now\b.*",
    r"\bsupported by\b.*",
    r"\bplayed by\b.*",
    r"\bavailable\b.*",
    r"\bout\s+(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b.*",
]

DEFAULT_REMOVE_PATTERNS = [
    r"\bfree download\b",
    r"\bofficial video in description\b",
    r"\bbuy = free\b",
    r"\bmusic video in description\b",
    r"\bclick buy\b",
    r"\bnew version in description\b",
    r"\bclick buy 4 free dl\b",
    r"\bbillboard premiere\b",
    r"\bbeatport\b",
    r"\brecords\b",
    r"\belectro house\b",
    r"\bpreview\b",
    r"\boriginal mix\b",
    r"\bradio edit\b",
    r"\bradio mix\b",
    r"\[mixmash\]",
]

SETTINGS_EXAMPLE_FILE = "parser_settings.example.json"
SETTINGS_LOCAL_FILE = "parser_settings.json"
SPOTIFY_SCOPES = [
    "playlist-modify-private",
    "playlist-modify-public",
]

# `SettingsLoader` is the point where unstructured configuration becomes typed
# application state. That keeps environment handling explicit and localized.
class SettingsLoader:
    """Load environment variables and parser settings into typed config objects."""

    def __init__(self, project_root: Path) -> None:
        """Bind the loader to the repository root used for files and secrets."""

        self.project_root = project_root

    # This supports the legacy local export path, which still expects concrete
    # file outputs and a fixed SoundCloud user target.
    def load_app_config(self) -> AppConfig:
        """Load settings for the legacy SoundCloud-to-Excel export flow."""

        self._load_environment()

        soundcloud_client_id = self._require_env("SOUNDCLOUD_CLIENT_ID")
        soundcloud_user_id = self._require_env("SOUNDCLOUD_USER_ID")

        return AppConfig(
            soundcloud_client_id=soundcloud_client_id,
            soundcloud_user_id=soundcloud_user_id,
            project_root=self.project_root,
            tracks_output_file=self.project_root / "soundcloud_likes.xlsx",
            livesets_output_file=self.project_root / "soundcloud_livesets.xlsx",
        )

    # Parser settings live outside the code so cleanup rules can evolve without
    # forcing users to edit Python modules directly.
    def load_parser_settings(self) -> ParserSettings:
        """Load parser overrides from JSON, falling back to repo defaults."""

        raw_settings = self._load_settings_payload()

        return ParserSettings(
            paren_keywords=self._get_string_list(
                raw_settings,
                "paren_keywords",
                DEFAULT_PAREN_KEYWORDS,
            ),
            liveset_keywords=self._get_string_list(
                raw_settings,
                "liveset_keywords",
                DEFAULT_LIVESET_KEYWORDS,
            ),
            cutoff_patterns=self._get_string_list(
                raw_settings,
                "cutoff_patterns",
                DEFAULT_CUTOFF_PATTERNS,
            ),
            remove_patterns=self._get_string_list(
                raw_settings,
                "remove_patterns",
                DEFAULT_REMOVE_PATTERNS,
            ),
        )

    # The CLI Spotify flow is retained as a separate config shape because it
    # has different runtime needs from the web app.
    def load_spotify_config(self) -> SpotifyConfig:
        """Load settings for the legacy CLI Spotify matching workflow."""

        self._load_environment()
        return SpotifyConfig(
            client_id=self._require_env("SPOTIFY_CLIENT_ID"),
            client_secret=self._require_env("SPOTIFY_CLIENT_SECRET"),
            redirect_uri=self._require_env("SPOTIFY_REDIRECT_URI"),
            token_file=self.project_root / "spotify_tokens.json",
            scopes=SPOTIFY_SCOPES.copy(),
        )

    # The web app and worker share this exact config contract so jobs behave
    # the same whether they are started locally or on Render.
    def load_web_app_config(self) -> WebAppConfig:
        """Load configuration required by the FastAPI app and queue worker."""

        self._load_environment()
        return WebAppConfig(
            project_root=self.project_root,
            database_url=self._get_env(
                "DATABASE_URL",
                f"sqlite:///{(self.project_root / 'webapp.sqlite3').as_posix()}",
            ),
            redis_url=self._get_env("REDIS_URL", "redis://localhost:6379/0"),
            session_secret=self._require_env("WEBAPP_SESSION_SECRET"),
            soundcloud_client_id=self._require_env("SOUNDCLOUD_CLIENT_ID"),
            spotify_client_id=self._require_env("SPOTIFY_CLIENT_ID"),
            spotify_client_secret=self._require_env("SPOTIFY_CLIENT_SECRET"),
            spotify_redirect_uri=self._require_env("WEBAPP_SPOTIFY_REDIRECT_URI"),
            spotify_scopes=SPOTIFY_SCOPES.copy(),
            app_base_url=self._get_env("APP_BASE_URL", "http://127.0.0.1:8000"),
            environment=self._get_env("APP_ENV", "development"),
        )

    # Loading from `.env` here keeps process startup simple and avoids
    # scattering dotenv calls across the codebase.
    def _load_environment(self) -> None:
        """Load environment variables from the local `.env` file if present."""

        load_dotenv(self.project_root / ".env")

    # Local parser settings take precedence, but the example file remains a
    # documented fallback for first-run and shared defaults.
    def _load_settings_payload(self) -> dict[str, object]:
        """Read parser settings from the local override or the example template."""

        local_path = self.project_root / SETTINGS_LOCAL_FILE
        example_path = self.project_root / SETTINGS_EXAMPLE_FILE

        if local_path.exists():
            return self._read_json(local_path)

        if example_path.exists():
            return self._read_json(example_path)

        return {}

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        """Read and validate that a JSON file contains a top-level object."""

        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        if not isinstance(payload, dict):
            raise ValueError(f"{path.name} must contain a JSON object.")

        return payload

    @staticmethod
    def _get_string_list(
        payload: dict[str, object],
        key: str,
        default: list[str],
    ) -> list[str]:
        """Return a list-of-strings setting or raise a clear validation error."""

        value = payload.get(key, default)

        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"'{key}' must be a list of strings.")

        return value

    @staticmethod
    def _require_env(name: str) -> str:
        """Return a required environment variable after trimming shell quotes."""

        value = os.getenv(name)
        if not value:
            raise ValueError(f"Missing {name} in environment.")
        return value.strip().strip("'").strip('"')

    @staticmethod
    def _get_env(name: str, default: str) -> str:
        """Return an environment variable with a default and normalized quoting."""

        value = os.getenv(name, default)
        return value.strip().strip("'").strip('"')
