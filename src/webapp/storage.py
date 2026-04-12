from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from src.models import PendingImportRequest, SpotifyTokens


@dataclass(frozen=True)
class ImportJob:
    id: str
    status: str
    soundcloud_user_id: str
    soundcloud_client_id: str
    playlist_name: str
    start_from_bottom: bool
    spotify_access_token: str
    spotify_refresh_token: str | None
    spotify_expires_at: int
    spotify_user_id: str | None
    spotify_display_name: str | None
    playlist_id: str | None
    playlist_url: str | None
    matched_count: int
    unmatched_count: int
    error_message: str | None
    created_at: str
    updated_at: str


class ImportJobStore:
    def __init__(self, database_file: Path) -> None:
        self.database_file = database_file
        self._initialize()

    def create_job(
        self,
        request: PendingImportRequest,
        soundcloud_client_id: str,
        spotify_tokens: SpotifyTokens,
        spotify_user_id: str | None,
        spotify_display_name: str | None,
    ) -> ImportJob:
        job_id = uuid4().hex
        timestamp = self._timestamp()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO import_jobs (
                    id,
                    status,
                    soundcloud_user_id,
                    soundcloud_client_id,
                    playlist_name,
                    start_from_bottom,
                    spotify_access_token,
                    spotify_refresh_token,
                    spotify_expires_at,
                    spotify_user_id,
                    spotify_display_name,
                    playlist_id,
                    playlist_url,
                    matched_count,
                    unmatched_count,
                    error_message,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    "pending",
                    request.soundcloud_user_id,
                    soundcloud_client_id,
                    request.playlist_name,
                    1 if request.start_from_bottom else 0,
                    spotify_tokens.access_token,
                    spotify_tokens.refresh_token,
                    spotify_tokens.expires_at,
                    spotify_user_id,
                    spotify_display_name,
                    None,
                    None,
                    0,
                    0,
                    None,
                    timestamp,
                    timestamp,
                ),
            )

        return self.get_job(job_id)

    def get_job(self, job_id: str) -> ImportJob:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM import_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()

        if row is None:
            raise KeyError(f"Import job not found: {job_id}")

        return self._row_to_job(row)

    def update_status(self, job_id: str, status: str, error_message: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE import_jobs
                SET status = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, error_message, self._timestamp(), job_id),
            )

    def update_spotify_tokens(self, job_id: str, tokens: SpotifyTokens) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE import_jobs
                SET spotify_access_token = ?,
                    spotify_refresh_token = ?,
                    spotify_expires_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    tokens.access_token,
                    tokens.refresh_token,
                    tokens.expires_at,
                    self._timestamp(),
                    job_id,
                ),
            )

    def mark_completed(
        self,
        job_id: str,
        matched_count: int,
        unmatched_count: int,
        playlist_id: str | None,
        playlist_url: str | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE import_jobs
                SET status = ?,
                    matched_count = ?,
                    unmatched_count = ?,
                    playlist_id = ?,
                    playlist_url = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    "completed",
                    matched_count,
                    unmatched_count,
                    playlist_id,
                    playlist_url,
                    self._timestamp(),
                    job_id,
                ),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_file)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        self.database_file.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS import_jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    soundcloud_user_id TEXT NOT NULL,
                    soundcloud_client_id TEXT NOT NULL,
                    playlist_name TEXT NOT NULL,
                    start_from_bottom INTEGER NOT NULL,
                    spotify_access_token TEXT NOT NULL,
                    spotify_refresh_token TEXT,
                    spotify_expires_at INTEGER NOT NULL,
                    spotify_user_id TEXT,
                    spotify_display_name TEXT,
                    playlist_id TEXT,
                    playlist_url TEXT,
                    matched_count INTEGER NOT NULL DEFAULT 0,
                    unmatched_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> ImportJob:
        return ImportJob(
            id=str(row["id"]),
            status=str(row["status"]),
            soundcloud_user_id=str(row["soundcloud_user_id"]),
            soundcloud_client_id=str(row["soundcloud_client_id"]),
            playlist_name=str(row["playlist_name"]),
            start_from_bottom=bool(row["start_from_bottom"]),
            spotify_access_token=str(row["spotify_access_token"]),
            spotify_refresh_token=str(row["spotify_refresh_token"]) if row["spotify_refresh_token"] else None,
            spotify_expires_at=int(row["spotify_expires_at"]),
            spotify_user_id=str(row["spotify_user_id"]) if row["spotify_user_id"] else None,
            spotify_display_name=str(row["spotify_display_name"]) if row["spotify_display_name"] else None,
            playlist_id=str(row["playlist_id"]) if row["playlist_id"] else None,
            playlist_url=str(row["playlist_url"]) if row["playlist_url"] else None,
            matched_count=int(row["matched_count"]),
            unmatched_count=int(row["unmatched_count"]),
            error_message=str(row["error_message"]) if row["error_message"] else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()
