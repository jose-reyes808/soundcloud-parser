from __future__ import annotations

"""Persistence layer for import jobs tracked by the web application."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from src.models import PendingImportRequest, SpotifyTokens

# `ImportJob` is the shape the rest of the application is allowed to see.
# It deliberately flattens the persistence model into an immutable record so
# route handlers and templates cannot accidentally couple themselves to ORM state.
@dataclass(frozen=True)
class ImportJob:
    """Immutable view model returned to the app and API layers."""

    id: str
    status: str
    current_phase: str | None
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
    total_tracks: int
    processed_tracks: int
    current_artist: str | None
    current_song: str | None
    matched_count: int
    unmatched_count: int
    error_message: str | None
    created_at: str
    updated_at: str


# Match review rows are stored separately from the job header so the status
# dashboard stays lightweight while the detailed audit view can grow richer.
@dataclass(frozen=True)
class ImportTrackResult:
    """Immutable review record for a single SoundCloud-to-Spotify match attempt."""

    id: int
    job_id: str
    row_index: int
    artist: str
    song: str
    original_title: str
    soundcloud_url: str | None
    match_status: str
    match_score: float | None
    spotify_matched_artist: str | None
    spotify_matched_song: str | None
    spotify_url: str | None
    spotify_search_query: str

# The declarative base stays local to this module to keep the database model
# from becoming a de facto global dependency for unrelated parts of the system.
class Base(DeclarativeBase):
    """SQLAlchemy declarative base for web-app persistence models."""

    pass

# The database record keeps both lifecycle state and fine-grained progress in
# one place. That choice makes polling simple and avoids stitching together job
# state from multiple tables before the product actually needs that complexity.
class ImportJobRecord(Base):
    """Database record representing one end-to-end playlist import job."""

    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_phase: Mapped[str | None] = mapped_column(String(64), nullable=True)
    soundcloud_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    soundcloud_client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    playlist_name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_from_bottom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    spotify_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    spotify_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    spotify_expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    spotify_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    spotify_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    playlist_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    playlist_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_tracks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_tracks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_artist: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_song: Mapped[str | None] = mapped_column(String(255), nullable=True)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmatched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# A separate review table keeps row-level match data queryable without bloating
# the primary job record or complicating the status polling path.
class ImportTrackResultRecord(Base):
    """Database record representing one row in the post-import review table."""

    __tablename__ = "import_track_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    artist: Mapped[str] = mapped_column(String(255), nullable=False)
    song: Mapped[str] = mapped_column(String(255), nullable=False)
    original_title: Mapped[str] = mapped_column(Text, nullable=False)
    soundcloud_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_status: Mapped[str] = mapped_column(String(32), nullable=False)
    match_score: Mapped[str | None] = mapped_column(String(32), nullable=True)
    spotify_matched_artist: Mapped[str | None] = mapped_column(Text, nullable=True)
    spotify_matched_song: Mapped[str | None] = mapped_column(Text, nullable=True)
    spotify_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    spotify_search_query: Mapped[str] = mapped_column(Text, nullable=False)

# `ImportJobStore` acts as the anti-corruption boundary around persistence.
# Everything above this layer works in terms of application events such as
# "create job" or "record progress", not sessions, commits, or ORM mutation.
class ImportJobStore:
    """Create, update, and retrieve import jobs from the configured database."""

    def __init__(self, database_url: str) -> None:
        """Initialize the SQLAlchemy engine and ensure the schema exists."""

        normalized_database_url = database_url
        if normalized_database_url.startswith("postgres://"):
            normalized_database_url = normalized_database_url.replace(
                "postgres://",
                "postgresql+psycopg://",
                1,
            )
        elif normalized_database_url.startswith("postgresql://"):
            normalized_database_url = normalized_database_url.replace(
                "postgresql://",
                "postgresql+psycopg://",
                1,
            )

        connect_args = {"check_same_thread": False} if normalized_database_url.startswith("sqlite") else {}
        self.engine = create_engine(
            normalized_database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, class_=Session)
        Base.metadata.create_all(self.engine)
        self._ensure_columns()

    # Persisting before enqueueing is intentional. It gives the user a stable
    # status URL immediately and avoids tying the callback response to worker
    # availability or queue latency.
    def create_job(
        self,
        request: PendingImportRequest,
        soundcloud_client_id: str,
        spotify_tokens: SpotifyTokens,
        spotify_user_id: str | None,
        spotify_display_name: str | None,
    ) -> ImportJob:
        """Persist a newly authorized import job before it enters the queue."""

        timestamp = self._timestamp()
        record = ImportJobRecord(
            id=uuid4().hex,
            status="pending",
            current_phase="Waiting for Spotify login",
            soundcloud_user_id=request.soundcloud_user_id,
            soundcloud_client_id=soundcloud_client_id,
            playlist_name=request.playlist_name,
            start_from_bottom=request.start_from_bottom,
            spotify_access_token=spotify_tokens.access_token,
            spotify_refresh_token=spotify_tokens.refresh_token,
            spotify_expires_at=spotify_tokens.expires_at,
            spotify_user_id=spotify_user_id,
            spotify_display_name=spotify_display_name,
            playlist_id=None,
            playlist_url=None,
            total_tracks=0,
            processed_tracks=0,
            current_artist=None,
            current_song=None,
            matched_count=0,
            unmatched_count=0,
            error_message=None,
            created_at=timestamp,
            updated_at=timestamp,
        )

        with self._session() as session:
            session.add(record)

        return self.get_job(record.id)

    def get_job(self, job_id: str) -> ImportJob:
        """Return a job by ID or raise `KeyError` if it does not exist."""

        with self._session() as session:
            record = session.get(ImportJobRecord, job_id)

        if record is None:
            raise KeyError(f"Import job not found: {job_id}")

        return self._record_to_job(record)

    def list_track_results(self, job_id: str) -> list[ImportTrackResult]:
        """Return all persisted track-level match results for a given job."""

        with self._session() as session:
            records = (
                session.query(ImportTrackResultRecord)
                .filter(ImportTrackResultRecord.job_id == job_id)
                .order_by(ImportTrackResultRecord.row_index.asc())
                .all()
            )

        return [self._record_to_track_result(record) for record in records]

    def update_status(
        self,
        job_id: str,
        status: str,
        error_message: str | None = None,
        current_phase: str | None = None,
    ) -> None:
        """Update the coarse-grained lifecycle state of an import job."""

        with self._session() as session:
            record = self._require_record(session, job_id)
            record.status = status
            record.error_message = error_message
            if current_phase is not None:
                record.current_phase = current_phase
            record.updated_at = self._timestamp()

    def update_spotify_tokens(self, job_id: str, tokens: SpotifyTokens) -> None:
        """Persist refreshed Spotify credentials for a long-running import job."""

        with self._session() as session:
            record = self._require_record(session, job_id)
            record.spotify_access_token = tokens.access_token
            record.spotify_refresh_token = tokens.refresh_token
            record.spotify_expires_at = tokens.expires_at
            record.updated_at = self._timestamp()

    def replace_track_results(
        self,
        job_id: str,
        results: list[ImportTrackResult],
    ) -> None:
        """Replace all review rows for a job with the latest matching output."""

        with self._session() as session:
            session.query(ImportTrackResultRecord).filter(
                ImportTrackResultRecord.job_id == job_id
            ).delete()
            for result in results:
                session.add(
                    ImportTrackResultRecord(
                        job_id=job_id,
                        row_index=result.row_index,
                        artist=result.artist,
                        song=result.song,
                        original_title=result.original_title,
                        soundcloud_url=result.soundcloud_url,
                        match_status=result.match_status,
                        match_score=str(result.match_score) if result.match_score is not None else None,
                        spotify_matched_artist=result.spotify_matched_artist,
                        spotify_matched_song=result.spotify_matched_song,
                        spotify_url=result.spotify_url,
                        spotify_search_query=result.spotify_search_query,
                    )
                )

    # Progress is stored as first-class application state rather than derived
    # from logs so the UI can present trustworthy status to users in real time.
    def update_progress(
        self,
        job_id: str,
        *,
        current_phase: str | None = None,
        total_tracks: int | None = None,
        processed_tracks: int | None = None,
        matched_count: int | None = None,
        unmatched_count: int | None = None,
        current_artist: str | None = None,
        current_song: str | None = None,
    ) -> None:
        """Persist fine-grained progress details shown on the status page."""

        with self._session() as session:
            record = self._require_record(session, job_id)
            if current_phase is not None:
                record.current_phase = current_phase
            if total_tracks is not None:
                record.total_tracks = total_tracks
            if processed_tracks is not None:
                record.processed_tracks = processed_tracks
            if matched_count is not None:
                record.matched_count = matched_count
            if unmatched_count is not None:
                record.unmatched_count = unmatched_count
            record.current_artist = current_artist
            record.current_song = current_song
            record.updated_at = self._timestamp()

    def mark_completed(
        self,
        job_id: str,
        matched_count: int,
        unmatched_count: int,
        playlist_id: str | None,
        playlist_url: str | None,
    ) -> None:
        """Mark a job as complete and record the resulting playlist metadata."""

        with self._session() as session:
            record = self._require_record(session, job_id)
            record.status = "completed"
            record.current_phase = "Completed"
            record.matched_count = matched_count
            record.unmatched_count = unmatched_count
            record.playlist_id = playlist_id
            record.playlist_url = playlist_url
            record.processed_tracks = record.total_tracks
            record.current_artist = None
            record.current_song = None
            record.updated_at = self._timestamp()

    def _require_record(self, session: Session, job_id: str) -> ImportJobRecord:
        """Load a database record or raise `KeyError` with a stable message."""

        record = session.get(ImportJobRecord, job_id)
        if record is None:
            raise KeyError(f"Import job not found: {job_id}")
        return record

    # Transaction handling is centralized here so every store method gets the
    # same commit-or-rollback semantics without repeating ceremony everywhere.
    def _session(self) -> Iterator[Session]:
        """Return a commit-or-rollback session context manager."""

        class _SessionContext:
            """Tiny context manager that centralizes SQLAlchemy session cleanup."""

            def __init__(self, session_factory: sessionmaker[Session]) -> None:
                self._session = session_factory()

            def __enter__(self) -> Session:
                return self._session

            def __exit__(self, exc_type, exc, tb) -> None:
                if exc_type is None:
                    self._session.commit()
                else:
                    self._session.rollback()
                self._session.close()

        return _SessionContext(self.session_factory)

    @staticmethod
    def _record_to_job(record: ImportJobRecord) -> ImportJob:
        """Map a mutable ORM record into the immutable public job model."""

        return ImportJob(
            id=record.id,
            status=record.status,
            current_phase=record.current_phase,
            soundcloud_user_id=record.soundcloud_user_id,
            soundcloud_client_id=record.soundcloud_client_id,
            playlist_name=record.playlist_name,
            start_from_bottom=record.start_from_bottom,
            spotify_access_token=record.spotify_access_token,
            spotify_refresh_token=record.spotify_refresh_token,
            spotify_expires_at=record.spotify_expires_at,
            spotify_user_id=record.spotify_user_id,
            spotify_display_name=record.spotify_display_name,
            playlist_id=record.playlist_id,
            playlist_url=record.playlist_url,
            total_tracks=record.total_tracks,
            processed_tracks=record.processed_tracks,
            current_artist=record.current_artist,
            current_song=record.current_song,
            matched_count=record.matched_count,
            unmatched_count=record.unmatched_count,
            error_message=record.error_message,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )

    @staticmethod
    def _record_to_track_result(record: ImportTrackResultRecord) -> ImportTrackResult:
        """Map a persisted review row into the immutable public result model."""

        return ImportTrackResult(
            id=record.id,
            job_id=record.job_id,
            row_index=record.row_index,
            artist=record.artist,
            song=record.song,
            original_title=record.original_title,
            soundcloud_url=record.soundcloud_url,
            match_status=record.match_status,
            match_score=float(record.match_score) if record.match_score is not None else None,
            spotify_matched_artist=record.spotify_matched_artist,
            spotify_matched_song=record.spotify_matched_song,
            spotify_url=record.spotify_url,
            spotify_search_query=record.spotify_search_query,
        )

    @staticmethod
    def _timestamp() -> datetime:
        """Generate a timezone-aware UTC timestamp for persistence fields."""

        return datetime.now(timezone.utc)

    # This is a pragmatic bridge while the schema is still evolving quickly.
    # It keeps existing local and deployed databases usable without introducing
    # a full migration stack before the data model settles.
    def _ensure_columns(self) -> None:
        """Add newer progress-tracking columns for existing databases.

        Render deployments may already have an older version of the table, so
        this lightweight migration keeps the app forward-compatible without a
        separate migration tool.
        """

        statements = [
            "ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS current_phase VARCHAR(64)",
            "ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS total_tracks INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS processed_tracks INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS current_artist VARCHAR(255)",
            "ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS current_song VARCHAR(255)",
        ]

        with self.engine.begin() as connection:
            for statement in statements:
                connection.exec_driver_sql(statement)
