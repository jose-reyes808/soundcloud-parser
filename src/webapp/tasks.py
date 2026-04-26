from __future__ import annotations

"""RQ task entrypoints invoked by the background worker."""

from pathlib import Path

from src.config import SettingsLoader
from src.webapp.import_runner import WebImportRunner
from src.webapp.spotify_oauth import SpotifyOAuthService
from src.webapp.storage import ImportJobStore

# The task function is intentionally thin. Its job is to reconstruct application
# services inside the worker process and then hand off to the real use-case code.
def run_import_job(job_id: str) -> None:
    """Bootstrap dependencies inside the worker and execute one import job."""

    project_root = Path(__file__).resolve().parents[2]
    settings_loader = SettingsLoader(project_root)
    web_config = settings_loader.load_web_app_config()
    store = ImportJobStore(web_config.database_url)
    oauth_service = SpotifyOAuthService(web_config)
    runner = WebImportRunner(settings_loader, store, oauth_service)
    runner.run_import(job_id)
