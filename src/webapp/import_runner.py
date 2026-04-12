from __future__ import annotations

from src.config import SettingsLoader
from src.models import PendingImportRequest, SpotifyTokens
from src.soundcloud.client import SoundCloudClient
from src.soundcloud.parser import SoundCloudTitleParser
from src.spotify.matcher import SpotifyTrackMatcher
from src.webapp.spotify_api import SpotifyApiClient
from src.webapp.spotify_oauth import SpotifyOAuthService
from src.webapp.storage import ImportJobStore


class WebImportRunner:
    def __init__(
        self,
        settings_loader: SettingsLoader,
        store: ImportJobStore,
        oauth_service: SpotifyOAuthService,
    ) -> None:
        self.settings_loader = settings_loader
        self.store = store
        self.oauth_service = oauth_service
        self.web_config = oauth_service.config

    def run_import(self, job_id: str) -> None:
        job = self.store.get_job(job_id)
        self.store.update_status(job_id, "running")

        try:
            parser_settings = self.settings_loader.load_parser_settings()
            title_parser = SoundCloudTitleParser(parser_settings)
            soundcloud_client = SoundCloudClient(
                client_id=self.web_config.soundcloud_client_id,
                user_id=job.soundcloud_user_id,
                title_parser=title_parser,
            )

            likes = soundcloud_client.get_likes()
            if not likes:
                raise ValueError(
                    "No SoundCloud likes were fetched. If you expected likes, the server-side "
                    "SOUNDCLOUD_CLIENT_ID is likely invalid, expired, or blocked."
                )
            if job.start_from_bottom:
                likes = list(reversed(likes))

            spotify_matcher = SpotifyTrackMatcher()
            tokens = SpotifyTokens(
                access_token=job.spotify_access_token,
                refresh_token=job.spotify_refresh_token,
                expires_at=job.spotify_expires_at,
            )
            spotify_api = SpotifyApiClient(
                tokens=tokens,
                refresh_tokens=self.oauth_service.refresh_tokens,
                persist_tokens=lambda refreshed_tokens: self.store.update_spotify_tokens(
                    job_id,
                    refreshed_tokens,
                ),
                request_timeout=self.oauth_service.config.request_timeout,
            )

            matched_uris: list[str] = []
            unmatched_count = 0

            for index, record in enumerate(likes, start=1):
                search_query = spotify_matcher.build_search_query(record.artist, record.song)
                candidates = spotify_api.search_tracks(search_query)
                match = spotify_matcher.match(record.artist, record.song, candidates, search_query)
                print(f"[web import {job_id}] {index}/{len(likes)} {record.artist} - {record.song}")

                if match is None:
                    unmatched_count += 1
                    continue

                matched_uris.append(match.spotify_uri)

            playlist = None
            if matched_uris:
                playlist = spotify_api.create_playlist(
                    name=job.playlist_name,
                    description="Imported from SoundCloud parser web app.",
                    public=False,
                )
                spotify_api.add_items_to_playlist(str(playlist["id"]), matched_uris)

            playlist_id = str(playlist["id"]) if playlist else None
            playlist_url_value = playlist.get("external_urls", {}).get("spotify") if playlist else None
            playlist_url = str(playlist_url_value) if playlist_url_value else None

            self.store.mark_completed(
                job_id=job_id,
                matched_count=len(matched_uris),
                unmatched_count=unmatched_count,
                playlist_id=playlist_id,
                playlist_url=playlist_url,
            )
        except Exception as error:
            self.store.update_status(job_id, "failed", error_message=str(error))
            raise
