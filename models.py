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
