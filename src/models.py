from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    soundcloud_client_id: str
    soundcloud_user_id: str
    project_root: Path
    tracks_output_file: Path
    livesets_output_file: Path


@dataclass(frozen=True)
class ParserSettings:
    paren_keywords: list[str] = field(default_factory=list)
    liveset_keywords: list[str] = field(default_factory=list)
    cutoff_patterns: list[str] = field(default_factory=list)
    remove_patterns: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TrackRecord:
    artist: str
    song: str
    artist_source: str
    original_title: str
    date_uploaded: str | None
    date_liked: str | None
    soundcloud_url: str | None

    def to_row(self) -> dict[str, str | None]:
        return {
            "Artist": self.artist,
            "Song": self.song,
            "Artist Source": self.artist_source,
            "Original Title": self.original_title,
            "Date Uploaded": self.date_uploaded,
            "Date Liked": self.date_liked,
            "SoundCloud URL": self.soundcloud_url,
        }


@dataclass(frozen=True)
class ExportResult:
    total_likes: int
    track_count: int
    liveset_count: int
    artist_source_breakdown: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SpotifyConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    token_file: Path
    scopes: list[str]
    request_timeout: int = 30


@dataclass(frozen=True)
class WebAppConfig:
    project_root: Path
    database_file: Path
    session_secret: str
    soundcloud_client_id: str
    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str
    spotify_scopes: list[str]
    app_base_url: str
    request_timeout: int = 30


@dataclass(frozen=True)
class SpotifyTokens:
    access_token: str
    refresh_token: str | None
    expires_at: int


@dataclass(frozen=True)
class PendingImportRequest:
    soundcloud_user_id: str
    playlist_name: str
    start_from_bottom: bool = False


@dataclass(frozen=True)
class SpotifyTrackMatch:
    spotify_track_id: str
    spotify_uri: str
    matched_artist: str
    matched_song: str
    match_score: float
    search_query: str
    album_name: str | None = None
    external_url: str | None = None


@dataclass(frozen=True)
class MatchRunSummary:
    rows_processed: int
    rows_matched: int
    rows_unmatched: int
    output_file: Path
    playlist_id: str | None = None
    playlist_url: str | None = None
