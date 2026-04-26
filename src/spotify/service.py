from __future__ import annotations

"""Legacy spreadsheet-driven Spotify matching workflow."""

from pathlib import Path

import pandas as pd

from src.models import MatchRunSummary
from src.spotify.client import SpotifyClient
from src.spotify.matcher import SpotifyTrackMatcher

# This service preserves the spreadsheet workflow as a well-bounded use case.
# That makes it easier to keep around without letting it shape the newer web app.
class SpotifyMatchService:
    """Match spreadsheet rows on Spotify and optionally create a playlist."""

    REQUIRED_COLUMNS = ["Artist", "Song"]

    def __init__(
        self,
        spotify_client: SpotifyClient,
        spotify_matcher: SpotifyTrackMatcher,
    ) -> None:
        """Compose the Spotify API client and the matching heuristic."""

        self.spotify_client = spotify_client
        self.spotify_matcher = spotify_matcher

    # This method is the orchestration layer for the legacy Excel flow and is
    # intentionally linear so it is easy to debug row by row.
    def run(
        self,
        input_file: Path,
        output_file: Path,
        create_playlist: bool = False,
        playlist_name: str | None = None,
        playlist_public: bool = False,
        start_from_bottom: bool = False,
    ) -> MatchRunSummary:
        """Execute the full spreadsheet matching workflow.

        Rows are read from Excel, matched against Spotify search results, written
        back to a new workbook, and optionally collected into a playlist.
        """

        dataframe = self._load_input_file(input_file)
        self._validate_columns(dataframe)
        if start_from_bottom:
            dataframe = dataframe.iloc[::-1].reset_index(drop=True)

        match_rows = []
        matched_uris: list[str] = []
        total_rows = len(dataframe)

        for row_index, (_, row) in enumerate(dataframe.iterrows(), start=1):
            artist = self._safe_cell(row.get("Artist"))
            song = self._safe_cell(row.get("Song"))
            search_queries = self.spotify_matcher.build_search_queries(
                artist,
                song,
                original_title=self._safe_cell(row.get("Original Title")),
                artist_source=self._safe_cell(row.get("Artist Source")),
            )
            search_query = search_queries[0]
            match = None
            for candidate_query in search_queries:
                candidates = self.spotify_client.search_tracks(candidate_query)
                candidate_match = self.spotify_matcher.match(
                    artist,
                    song,
                    candidates,
                    candidate_query,
                )
                if candidate_match is not None:
                    search_query = candidate_query
                    match = candidate_match
                    break

            print(f"[{row_index}/{total_rows}] Matching {artist} - {song}")

            row_data = row.to_dict()
            if match is None:
                row_data.update(
                    {
                        "Spotify Match Status": "No Match",
                        "Spotify Search Query": search_query,
                        "Spotify Match Score": None,
                        "Spotify Track ID": None,
                        "Spotify URI": None,
                        "Spotify Matched Artist": None,
                        "Spotify Matched Song": None,
                        "Spotify Album": None,
                        "Spotify URL": None,
                    }
                )
            else:
                matched_uris.append(match.spotify_uri)
                row_data.update(
                    {
                        "Spotify Match Status": "Matched",
                        "Spotify Search Query": match.search_query,
                        "Spotify Match Score": match.match_score,
                        "Spotify Track ID": match.spotify_track_id,
                        "Spotify URI": match.spotify_uri,
                        "Spotify Matched Artist": match.matched_artist,
                        "Spotify Matched Song": match.matched_song,
                        "Spotify Album": match.album_name,
                        "Spotify URL": match.external_url,
                    }
                )

            match_rows.append(row_data)

        output_dataframe = pd.DataFrame(match_rows)
        output_dataframe.to_excel(output_file, index=False)

        playlist_id = None
        playlist_url = None
        if create_playlist and matched_uris:
            playlist = self.spotify_client.create_playlist(
                name=playlist_name or "SoundCloud Imports",
                description="Imported from SoundCloud parser matches.",
                public=playlist_public,
            )
            playlist_id = str(playlist.get("id"))
            playlist_url_value = playlist.get("external_urls", {}).get("spotify")
            playlist_url = str(playlist_url_value) if playlist_url_value else None
            self.spotify_client.add_items_to_playlist(playlist_id, matched_uris)

        return MatchRunSummary(
            rows_processed=len(output_dataframe),
            rows_matched=len(matched_uris),
            rows_unmatched=len(output_dataframe) - len(matched_uris),
            output_file=output_file,
            playlist_id=playlist_id,
            playlist_url=playlist_url,
        )

    @classmethod
    # Early validation keeps the matching loop simple and produces a clearer
    # failure than letting missing columns surface later as KeyErrors.
    def _validate_columns(cls, dataframe: pd.DataFrame) -> None:
        """Ensure the input sheet contains the columns needed for matching."""

        missing_columns = [
            column_name for column_name in cls.REQUIRED_COLUMNS if column_name not in dataframe.columns
        ]
        if missing_columns:
            missing_list = ", ".join(missing_columns)
            raise ValueError(f"Input file is missing required columns: {missing_list}")

    @staticmethod
    def _load_input_file(input_file: Path) -> pd.DataFrame:
        """Load the input workbook from disk with a clear missing-file error."""

        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

        return pd.read_excel(input_file)

    @staticmethod
    def _safe_cell(value: object) -> str:
        """Normalize a spreadsheet cell into a stripped string value."""

        if value is None or pd.isna(value):
            return ""
        return str(value).strip()
