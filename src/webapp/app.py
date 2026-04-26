from __future__ import annotations

"""FastAPI application factory and routes for the public web experience."""

import logging
from pathlib import Path

import requests
from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from src.config import SettingsLoader
from src.models import PendingImportRequest, SoundCloudTokens
from src.soundcloud.client import SoundCloudClient
from src.webapp.queue import create_queue
from src.webapp.soundcloud_api import SoundCloudApiClient
from src.webapp.soundcloud_oauth import SoundCloudOAuthService
from src.webapp.spotify_oauth import SpotifyOAuthService
from src.webapp.storage import ImportJobStore
from src.webapp.tasks import run_import_job


logger = logging.getLogger(__name__)

# This factory is the composition root for the deployed application. Keeping
# dependency assembly here makes the request layer straightforward and prevents
# infrastructure concerns from leaking into the route handlers themselves.
def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    The app owns the web-facing flow: accept user input, start Spotify OAuth,
    create import jobs after the callback, and expose both HTML pages and a
    lightweight JSON endpoint for live progress updates.
    """

    project_root = Path(__file__).resolve().parents[2]
    settings_loader = SettingsLoader(project_root)
    web_config = settings_loader.load_web_app_config()
    templates = Jinja2Templates(directory=str(project_root / "templates"))
    store = ImportJobStore(web_config.database_url)
    oauth_service = SpotifyOAuthService(web_config)
    soundcloud_oauth_service = SoundCloudOAuthService(web_config)
    queue = create_queue(web_config.redis_url)

    app = FastAPI(title="SoundCloud Parser Web App")
    app.add_middleware(SessionMiddleware, secret_key=web_config.session_secret)

    def serialize_soundcloud_tokens(tokens: SoundCloudTokens) -> dict[str, str | int | None]:
        return {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expires_at": tokens.expires_at,
        }

    def load_soundcloud_tokens(request: Request) -> SoundCloudTokens | None:
        payload = request.session.get("soundcloud_tokens")
        if not isinstance(payload, dict):
            return None
        access_token = payload.get("access_token")
        expires_at = payload.get("expires_at")
        if not isinstance(access_token, str) or not isinstance(expires_at, int):
            return None
        refresh_token = payload.get("refresh_token")
        return SoundCloudTokens(
            access_token=access_token,
            refresh_token=str(refresh_token) if refresh_token else None,
            expires_at=expires_at,
        )

    # The landing page doubles as the place where user-facing flash messages
    # are surfaced after redirects and failed initialization attempts.
    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        """Render the landing page and surface any flash message from redirects."""

        flash_message = request.session.pop("flash_message", None)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "flash_message": flash_message,
                "app_base_url": web_config.app_base_url,
            },
        )

    @app.get("/auth/soundcloud/start")
    async def soundcloud_start(
        request: Request,
        job_id: str = Query(...),
    ) -> RedirectResponse:
        """Start the SoundCloud OAuth flow for the results review experience."""

        try:
            store.get_job(job_id)
        except KeyError:
            request.session["flash_message"] = "That import job could not be found."
            return RedirectResponse("/", status_code=303)

        state = soundcloud_oauth_service.generate_state()
        code_verifier = soundcloud_oauth_service.generate_code_verifier()
        code_challenge = soundcloud_oauth_service.build_code_challenge(code_verifier)

        request.session["soundcloud_oauth_state"] = state
        request.session["soundcloud_code_verifier"] = code_verifier
        request.session["soundcloud_return_to"] = f"/imports/{job_id}/results"

        return RedirectResponse(
            soundcloud_oauth_service.build_authorize_url(state, code_challenge),
            status_code=303,
        )

    @app.get("/auth/soundcloud/callback")
    async def soundcloud_callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> RedirectResponse:
        """Complete SoundCloud OAuth and store user tokens in the session."""

        return_to = str(request.session.get("soundcloud_return_to") or "/")

        if error:
            request.session["flash_message"] = f"SoundCloud authorization failed: {error}"
            return RedirectResponse(return_to, status_code=303)

        expected_state = request.session.get("soundcloud_oauth_state")
        code_verifier = request.session.get("soundcloud_code_verifier")
        if (
            not code
            or not state
            or state != expected_state
            or not isinstance(code_verifier, str)
        ):
            request.session["flash_message"] = "SoundCloud authorization could not be completed."
            return RedirectResponse(return_to, status_code=303)

        try:
            tokens = soundcloud_oauth_service.exchange_code(code, code_verifier)
            profile = soundcloud_oauth_service.get_current_user_profile(tokens.access_token)
            request.session["soundcloud_tokens"] = serialize_soundcloud_tokens(tokens)
            request.session["soundcloud_profile_name"] = str(
                profile.get("full_name") or profile.get("username") or "Connected SoundCloud account"
            )
            request.session.pop("soundcloud_oauth_state", None)
            request.session.pop("soundcloud_code_verifier", None)
            request.session["flash_message"] = "SoundCloud connected. You can now create SoundCloud playlists from these results."
        except Exception:
            logger.exception("SoundCloud callback failed during authorization.")
            request.session["flash_message"] = "SoundCloud login succeeded, but the app could not complete the connection."

        return RedirectResponse(return_to, status_code=303)

    # Import startup does only the work required before OAuth: validate input,
    # resolve the SoundCloud profile, and stash a pending request in session.
    @app.post("/imports/start")
    async def start_import(
        request: Request,
        soundcloud_profile_url: str = Form(...),
        playlist_name: str = Form("SoundCloud Likes"),
        start_from_bottom: str | None = Form(None),
    ) -> RedirectResponse:
        """Validate the request, resolve the SoundCloud user, and start OAuth."""

        try:
            soundcloud_user_id = SoundCloudClient.resolve_user_id(
                client_id=web_config.soundcloud_client_id,
                profile_input=soundcloud_profile_url,
                request_timeout=web_config.request_timeout,
            )
        except Exception as error:
            request.session["flash_message"] = f"SoundCloud profile could not be resolved: {error}"
            return RedirectResponse("/", status_code=303)

        pending_request = PendingImportRequest(
            soundcloud_user_id=soundcloud_user_id,
            playlist_name=playlist_name.strip() or "SoundCloud Likes",
            start_from_bottom=start_from_bottom == "on",
        )
        oauth_state = oauth_service.generate_state()

        request.session["pending_import"] = {
            "soundcloud_profile_url": soundcloud_profile_url.strip(),
            "soundcloud_user_id": pending_request.soundcloud_user_id,
            "playlist_name": pending_request.playlist_name,
            "start_from_bottom": pending_request.start_from_bottom,
        }
        request.session["spotify_oauth_state"] = oauth_state

        return RedirectResponse(
            oauth_service.build_authorize_url(oauth_state),
            status_code=303,
        )

    # The callback finishes authorization, creates a durable job record, and
    # hands the expensive work off to the background queue.
    @app.get("/auth/spotify/callback")
    async def spotify_callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> RedirectResponse:
        """Complete Spotify OAuth and enqueue the background import job."""

        if error:
            request.session["flash_message"] = f"Spotify authorization failed: {error}"
            return RedirectResponse("/", status_code=303)

        expected_state = request.session.get("spotify_oauth_state")
        pending_payload = request.session.get("pending_import")

        if not code or not state or state != expected_state or not pending_payload:
            request.session["flash_message"] = "Spotify authorization could not be completed."
            return RedirectResponse("/", status_code=303)

        try:
            tokens = oauth_service.exchange_code(code)
            profile = oauth_service.get_current_user_profile(tokens.access_token)

            pending_request = PendingImportRequest(
                soundcloud_user_id=str(pending_payload["soundcloud_user_id"]),
                playlist_name=str(pending_payload["playlist_name"]),
                start_from_bottom=bool(pending_payload["start_from_bottom"]),
            )

            job = store.create_job(
                request=pending_request,
                soundcloud_client_id=web_config.soundcloud_client_id,
                spotify_tokens=tokens,
                spotify_user_id=str(profile.get("id")) if profile.get("id") else None,
                spotify_display_name=str(profile.get("display_name")) if profile.get("display_name") else None,
            )

            request.session.pop("pending_import", None)
            request.session.pop("spotify_oauth_state", None)
            queue.enqueue(run_import_job, job.id, job_timeout="30m")
        except requests.exceptions.HTTPError as error:
            logger.exception("Spotify callback failed during import initialization.")
            if error.response is not None and error.response.status_code == 403:
                request.session["flash_message"] = (
                    "Spotify login succeeded, but this Spotify account is not authorized for this app yet. "
                    "The app owner needs to add your Spotify name and email to the app's authorized users "
                    "in the Spotify Developer Dashboard."
                )
            else:
                request.session["flash_message"] = (
                    "Spotify login succeeded, but the import could not be started. "
                    "Please try again in a moment."
                )
            return RedirectResponse("/", status_code=303)
        except Exception:
            logger.exception("Spotify callback failed during import initialization.")
            request.session["flash_message"] = (
                "Spotify login succeeded, but the import could not be started. "
                "Please try again in a moment."
            )
            return RedirectResponse("/", status_code=303)

        return RedirectResponse(f"/imports/{job.id}", status_code=303)

    # The HTML status route is intentionally separate from the JSON endpoint so
    # the frontend can stay simple and server-rendered.
    @app.get("/imports/{job_id}", response_class=HTMLResponse)
    async def import_status(request: Request, job_id: str) -> HTMLResponse:
        """Render the status dashboard for a single import job."""

        try:
            job = store.get_job(job_id)
        except KeyError:
            return templates.TemplateResponse(
                request=request,
                name="import_not_found.html",
                context={"job_id": job_id},
                status_code=404,
            )

        flash_message = request.session.pop("flash_message", None)
        return templates.TemplateResponse(
            request=request,
            name="import_status.html",
            context={
                "job": job,
                "flash_message": flash_message,
                "soundcloud_connected": load_soundcloud_tokens(request) is not None,
            },
        )

    @app.get("/imports/{job_id}/results", response_class=HTMLResponse)
    async def import_results(
        request: Request,
        job_id: str,
        status: str = Query("all"),
    ) -> HTMLResponse:
        """Render a detailed review page for track-level match results."""

        try:
            job = store.get_job(job_id)
        except KeyError:
            return templates.TemplateResponse(
                request=request,
                name="import_not_found.html",
                context={"job_id": job_id},
                status_code=404,
            )

        results = store.list_track_results(job_id)
        normalized_status = status.lower().strip()
        if normalized_status == "matched":
            results = [result for result in results if result.match_status == "Matched"]
        elif normalized_status == "unmatched":
            results = [result for result in results if result.match_status == "Unmatched"]
        else:
            normalized_status = "all"

        flash_message = request.session.pop("flash_message", None)
        return templates.TemplateResponse(
            request=request,
            name="import_results.html",
            context={
                "job": job,
                "results": results,
                "selected_status": normalized_status,
                "flash_message": flash_message,
                "soundcloud_connected": load_soundcloud_tokens(request) is not None,
                "soundcloud_profile_name": request.session.get("soundcloud_profile_name"),
            },
        )

    @app.post("/imports/{job_id}/soundcloud-playlists/{playlist_kind}")
    async def create_soundcloud_playlist(
        request: Request,
        job_id: str,
        playlist_kind: str,
    ) -> RedirectResponse:
        """Create a SoundCloud playlist from persisted import review rows."""

        try:
            job = store.get_job(job_id)
        except KeyError:
            request.session["flash_message"] = "That import job could not be found."
            return RedirectResponse("/", status_code=303)

        tokens = load_soundcloud_tokens(request)
        if tokens is None:
            request.session["flash_message"] = "Connect SoundCloud before creating SoundCloud playlists."
            return RedirectResponse(f"/auth/soundcloud/start?job_id={job_id}", status_code=303)

        results = store.list_track_results(job_id)
        normalized_kind = playlist_kind.lower().strip()
        if normalized_kind == "livesets":
            selected_rows = [row for row in results if row.is_liveset]
            playlist_title = "SoundCloud Livesets"
            playlist_description = f"Livesets imported from {job.playlist_name} via SoundCloud Parser."
        elif normalized_kind == "exclusives":
            selected_rows = [
                row for row in results if (not row.is_liveset) and row.match_status == "Unmatched"
            ]
            playlist_title = "SoundCloud Exclusives"
            playlist_description = (
                f"Tracks from {job.playlist_name} that were not matched on Spotify."
            )
        else:
            request.session["flash_message"] = "Unknown SoundCloud playlist type."
            return RedirectResponse(f"/imports/{job_id}/results", status_code=303)

        track_ids: list[str] = []
        seen_ids: set[str] = set()
        for row in selected_rows:
            if not row.soundcloud_track_id or row.soundcloud_track_id in seen_ids:
                continue
            seen_ids.add(row.soundcloud_track_id)
            track_ids.append(row.soundcloud_track_id)

        if not track_ids:
            request.session["flash_message"] = f"No tracks were available for {playlist_title}."
            return RedirectResponse(f"/imports/{job_id}/results", status_code=303)

        def persist_tokens(refreshed_tokens: SoundCloudTokens) -> None:
            request.session["soundcloud_tokens"] = serialize_soundcloud_tokens(refreshed_tokens)

        soundcloud_api = SoundCloudApiClient(
            tokens=tokens,
            refresh_tokens=soundcloud_oauth_service.refresh_tokens,
            persist_tokens=persist_tokens,
            request_timeout=web_config.request_timeout,
        )

        try:
            playlist, accepted_ids, skipped_ids = soundcloud_api.create_playlist_best_effort(
                title=playlist_title,
                track_ids=track_ids,
                description=playlist_description,
                sharing="private",
            )
            persist_tokens(soundcloud_api.tokens)
            playlist_url = playlist.get("permalink_url")
            if skipped_ids:
                request.session["flash_message"] = (
                    f"{playlist_title} created with {len(accepted_ids)} tracks. "
                    f"{len(skipped_ids)} tracks were skipped because SoundCloud would not accept them."
                    if not playlist_url
                    else f"{playlist_title} created with {len(accepted_ids)} tracks and {len(skipped_ids)} skipped: {playlist_url}"
                )
            else:
                request.session["flash_message"] = (
                    f"{playlist_title} created successfully."
                    if playlist_url is None
                    else f"{playlist_title} created successfully: {playlist_url}"
                )
        except Exception:
            logger.exception("SoundCloud playlist creation failed.")
            request.session["flash_message"] = f"The app could not create {playlist_title}."

        return RedirectResponse(f"/imports/{job_id}/results", status_code=303)

    # Polling this endpoint keeps the UI lightweight while still showing real
    # progress from the worker.
    @app.get("/api/imports/{job_id}", response_class=JSONResponse)
    async def import_status_api(job_id: str) -> JSONResponse:
        """Expose machine-readable job progress for polling from the UI."""

        try:
            job = store.get_job(job_id)
        except KeyError:
            return JSONResponse({"error": "Import job not found."}, status_code=404)

        progress_percentage = 0
        if job.total_tracks > 0:
            progress_percentage = round((job.processed_tracks / job.total_tracks) * 100, 1)

        return JSONResponse(
            {
                "id": job.id,
                "status": job.status,
                "current_phase": job.current_phase,
                "soundcloud_user_id": job.soundcloud_user_id,
                "playlist_name": job.playlist_name,
                "spotify_display_name": job.spotify_display_name,
                "spotify_user_id": job.spotify_user_id,
                "matched_count": job.matched_count,
                "unmatched_count": job.unmatched_count,
                "total_tracks": job.total_tracks,
                "processed_tracks": job.processed_tracks,
                "current_artist": job.current_artist,
                "current_song": job.current_song,
                "playlist_url": job.playlist_url,
                "error_message": job.error_message,
                "progress_percentage": progress_percentage,
            }
        )

    return app
