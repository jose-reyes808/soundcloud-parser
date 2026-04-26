from __future__ import annotations

"""Core data models shared across the SoundCloud and Spotify workflows."""

from dataclasses import asdict, dataclass, field
from pathlib import Path


# These models define the shared language of the application. Making that
# language explicit keeps boundaries clear and prevents the codebase from
# devolving into loosely structured dictionaries passed between layers.
@dataclass(frozen=True)
class AppConfig:
    """Configuration required by the legacy local SoundCloud export workflow."""

    soundcloud_client_id: str
    soundcloud_user_id: str
    project_root: Path
    tracks_output_file: Path
    livesets_output_file: Path


# Parser settings stay external to the code because title cleanup is a living
# rule set. It changes with the data, not with the architecture.
@dataclass(frozen=True)
class ParserSettings:
    """User-editable parsing rules used to normalize SoundCloud titles."""

    paren_keywords: list[str] = field(default_factory=list)
    liveset_keywords: list[str] = field(default_factory=list)
    cutoff_patterns: list[str] = field(default_factory=list)
    remove_patterns: list[str] = field(default_factory=list)


# `TrackRecord` is the canonical output of the SoundCloud side of the pipeline.
# Once data reaches this shape, downstream code can stop thinking about raw API
# payloads and focus on business logic.
@dataclass(frozen=True)
class TrackRecord:
    """Normalized representation of a single liked SoundCloud track."""

    artist: str
    song: str
    artist_source: str
    original_title: str
    date_uploaded: str | None
    date_liked: str | None
    soundcloud_url: str | None

    def to_row(self) -> dict[str, str | None]:
        """Convert the record into a spreadsheet-friendly row payload."""

        return {
            "Artist": self.artist,
            "Song": self.song,
            "Artist Source": self.artist_source,
            "Original Title": self.original_title,
            "Date Uploaded": self.date_uploaded,
            "Date Liked": self.date_liked,
            "SoundCloud URL": self.soundcloud_url,
        }


# Export summaries make the side effects of the legacy spreadsheet workflow
# observable without forcing callers to inspect the generated files.
@dataclass(frozen=True)
class ExportResult:
    """Summary returned after exporting SoundCloud likes to Excel workbooks."""

    total_likes: int
    track_count: int
    liveset_count: int
    artist_source_breakdown: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        """Serialize the export summary into plain Python data."""

        return asdict(self)


# The CLI and web app have different operational concerns, so their configs are
# modeled separately instead of pretending one settings object fits both worlds.
@dataclass(frozen=True)
class SpotifyConfig:
    """Credentials and runtime settings for the CLI Spotify client."""

    client_id: str
    client_secret: str
    redirect_uri: str
    token_file: Path
    scopes: list[str]
    request_timeout: int = 30


# The web app and the worker are two processes serving one product. A shared
# config model keeps them aligned on OAuth, storage, and queue assumptions.
@dataclass(frozen=True)
class WebAppConfig:
    """Configuration consumed by the FastAPI web app and background worker."""

    project_root: Path
    database_url: str
    redis_url: str
    session_secret: str
    soundcloud_client_id: str
    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str
    spotify_scopes: list[str]
    app_base_url: str
    environment: str = "development"
    request_timeout: int = 30


# OAuth tokens are treated as domain data because expiration and refresh are
# central to the reliability of long-running imports.
@dataclass(frozen=True)
class SpotifyTokens:
    """Spotify OAuth token bundle with its computed expiration timestamp."""

    access_token: str
    refresh_token: str | None
    expires_at: int


# This object exists specifically to survive the OAuth redirect boundary, so it
# stays small, serializable, and free of incidental runtime state.
@dataclass(frozen=True)
class PendingImportRequest:
    """Lightweight request payload stored during the web OAuth handoff."""

    soundcloud_user_id: str
    playlist_name: str
    start_from_bottom: bool = False


# Matching returns an application-level object rather than a raw Spotify record
# so later layers can depend on intent, not vendor response shape.
@dataclass(frozen=True)
class SpotifyTrackMatch:
    """Best-match result returned by the Spotify matching pipeline."""

    spotify_track_id: str
    spotify_uri: str
    matched_artist: str
    matched_song: str
    match_score: float
    search_query: str
    album_name: str | None = None
    external_url: str | None = None


# The legacy matching flow is heavily side-effect driven, so this summary gives
# scripts and tests something concrete to assert on.
@dataclass(frozen=True)
class MatchRunSummary:
    """Summary of a completed Spotify matching run."""

    rows_processed: int
    rows_matched: int
    rows_unmatched: int
    output_file: Path
    playlist_id: str | None = None
    playlist_url: str | None = None
