from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from models import AppConfig, ParserSettings


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


class SettingsLoader:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def load_app_config(self) -> AppConfig:
        load_dotenv(self.project_root / ".env")

        soundcloud_client_id = self._require_env("SOUNDCLOUD_CLIENT_ID")
        soundcloud_user_id = self._require_env("SOUNDCLOUD_USER_ID")

        return AppConfig(
            soundcloud_client_id=soundcloud_client_id,
            soundcloud_user_id=soundcloud_user_id,
            project_root=self.project_root,
            tracks_output_file=self.project_root / "soundcloud_likes.xlsx",
            livesets_output_file=self.project_root / "soundcloud_livesets.xlsx",
        )

    def load_parser_settings(self) -> ParserSettings:
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

    def _load_settings_payload(self) -> dict[str, object]:
        local_path = self.project_root / SETTINGS_LOCAL_FILE
        example_path = self.project_root / SETTINGS_EXAMPLE_FILE

        if local_path.exists():
            return self._read_json(local_path)

        if example_path.exists():
            return self._read_json(example_path)

        return {}

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
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
        value = payload.get(key, default)

        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"'{key}' must be a list of strings.")

        return value

    @staticmethod
    def _require_env(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise ValueError(f"Missing {name} in environment.")
        return value.strip().strip("'").strip('"')
